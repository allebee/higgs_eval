"""Async runner with concurrency cap and retry-on-transient-only policy.

Key invariants:
* Assertion failures never retry.
* Retries fire only on 429, 5xx, and network-like errors; everything else
  (including bad-request 4xx from the agent's Anthropic call) surfaces as
  an error trace for the scorer to judge.
* The semaphore keeps us from thundering-herd against Anthropic. Concurrency
  is configurable via --concurrency or DRLEVAL_CONCURRENCY.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Callable

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from .agent_adapter import default_agent, save_trace
from .schema import Case, CaseAggregate, CaseRunResult, Trace
from .scorer import score


def _transient_types() -> tuple[type, ...]:
    """Import Anthropic exception classes lazily; degrade to empty if missing."""
    try:
        from anthropic import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )

        return (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError, APIStatusError)
    except Exception:
        return ()


_TRANSIENT = _transient_types()


def _is_transient(e: BaseException) -> bool:
    if _TRANSIENT and isinstance(e, _TRANSIENT):
        # APIStatusError covers 5xx and some 4xx; only retry 5xx / 429.
        status = getattr(e, "status_code", None)
        if status is None or status == 429 or (500 <= int(status) < 600):
            return True
    if isinstance(e, (TimeoutError, ConnectionError)):
        return True
    msg = str(e).lower()
    return any(s in msg for s in ("429", "timeout", "connection", "overloaded", "502", "503", "504"))


class BudgetExceeded(RuntimeError):
    """Raised when cumulative API cost exceeds DRLEVAL_MAX_USD."""


AgentFactory = Callable[[str, int], Callable[[str], Trace]]


class _CostGovernor:
    """Best-effort circuit breaker on cumulative spend.

    Best-effort because in-flight tasks already past the gate will still
    complete; we just stop admitting new runs.
    """

    def __init__(self, max_usd: float) -> None:
        self.max_usd = max_usd
        self.spent = 0.0
        self._lock = asyncio.Lock()
        self.tripped = False

    async def admit(self) -> bool:
        async with self._lock:
            if self.max_usd <= 0:
                return True
            if self.spent >= self.max_usd:
                self.tripped = True
                return False
            return True

    async def record(self, usd: float) -> None:
        async with self._lock:
            self.spent += usd


async def _run_one(
    case: Case,
    run_index: int,
    *,
    traces_dir: Path,
    agent_factory: AgentFactory,
    judge: Any,
    loop: asyncio.AbstractEventLoop,
    governor: "_CostGovernor | None" = None,
) -> CaseRunResult:
    async def _call() -> Trace:
        fn = agent_factory(case.id, run_index)
        # agent is sync; run in executor to avoid blocking the loop.
        return await loop.run_in_executor(None, fn, case.input)

    if governor is not None and not await governor.admit():
        trace = _error_trace(case, run_index, "BudgetExceeded: DRLEVAL_MAX_USD hit; run skipped")
        trace_path = save_trace(trace, traces_dir)
        result = score(case, trace, judge=judge)
        result.trace_path = str(trace_path)
        return result

    try:
        # Tuned for Anthropic's per-minute input-token bucket (~50k tok/min on
        # Tier 1). A 429 typically clears within ~60s of the bucket refilling,
        # so the retry budget must cover at least one full window.
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential_jitter(initial=4, max=60),
            retry=retry_if_exception(_is_transient),
            reraise=True,
        ):
            with attempt:
                trace = await _call()
    except RetryError as e:
        trace = _error_trace(case, run_index, f"RetryError: {e}")
    except Exception as e:  # non-transient — one error trace, no retries
        trace = _error_trace(case, run_index, f"{type(e).__name__}: {e}")

    trace_path = save_trace(trace, traces_dir)
    result = score(case, trace, judge=judge)
    result.trace_path = str(trace_path)
    if governor is not None:
        await governor.record(result.cost_usd)
    return result


def _error_trace(case: Case, run_index: int, err: str) -> Trace:
    import uuid

    return Trace(
        run_id=str(uuid.uuid4()),
        case_id=case.id,
        run_index=run_index,
        question=case.input,
        model=os.getenv("DRL_MODEL", "claude-haiku-4-5"),
        messages=[],
        final_answer=None,
        citations=[],
        stopped_reason="error",
        error=err,
    )


async def run_suite(
    cases: list[Case],
    *,
    traces_dir: Path,
    concurrency: int = 4,
    repeats: int | None = None,
    agent_factory: AgentFactory | None = None,
    judge: Any = None,
    max_usd: float = 0.0,
) -> list[CaseAggregate]:
    loop = asyncio.get_event_loop()
    sem = asyncio.Semaphore(concurrency)
    agent_factory = agent_factory or default_agent
    governor = _CostGovernor(max_usd) if max_usd > 0 else None

    async def _guarded(case: Case, idx: int) -> CaseRunResult:
        async with sem:
            return await _run_one(
                case,
                idx,
                traces_dir=traces_dir,
                agent_factory=agent_factory,
                judge=judge,
                loop=loop,
                governor=governor,
            )

    tasks: list[asyncio.Task] = []
    case_of_task: list[Case] = []
    for case in cases:
        n = repeats if repeats is not None else case.repeats
        for i in range(n):
            tasks.append(asyncio.create_task(_guarded(case, i)))
            case_of_task.append(case)

    results: dict[str, list[CaseRunResult]] = {c.id: [] for c in cases}
    for task, case in zip(tasks, case_of_task):
        r = await task
        results[case.id].append(r)

    out: list[CaseAggregate] = []
    for case in cases:
        runs = sorted(results[case.id], key=lambda r: r.run_index)
        out.append(CaseAggregate(case_id=case.id, runs=runs))
    return out


def run_suite_sync(cases: list[Case], **kwargs: Any) -> list[CaseAggregate]:
    return asyncio.run(run_suite(cases, **kwargs))


# -- Replay-mode scoring -----------------------------------------------------


def rescore_from_traces(
    cases: list[Case],
    traces_dir: Path,
    *,
    judge: Any = None,
) -> list[CaseAggregate]:
    from .agent_adapter import load_trace

    by_case: dict[str, list[CaseRunResult]] = {c.id: [] for c in cases}
    case_map = {c.id: c for c in cases}

    for p in sorted(traces_dir.glob("*.json")):
        try:
            trace = load_trace(p)
        except Exception:
            continue
        case = case_map.get(trace.case_id)
        if case is None:
            continue
        r = score(case, trace, judge=judge)
        r.trace_path = str(p)
        by_case[case.id].append(r)

    return [CaseAggregate(case_id=c.id, runs=sorted(by_case[c.id], key=lambda r: r.run_index)) for c in cases]
