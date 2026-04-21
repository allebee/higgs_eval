"""Tests for retry classification and the cost governor."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest

from drleval.judge import StubJudge
from drleval.loader import load_cases
from drleval.runner import _is_transient, run_suite
from drleval.schema import Trace


def test_is_transient_on_timeout_and_connection():
    assert _is_transient(TimeoutError("read timeout"))
    assert _is_transient(ConnectionError("connection reset"))


def test_is_transient_on_message_substrings():
    class FakeErr(Exception):
        pass

    assert _is_transient(FakeErr("429 rate limit hit"))
    assert _is_transient(FakeErr("upstream 503 overloaded"))


def test_is_not_transient_on_bad_request():
    class FakeErr(Exception):
        pass

    # A plain bad-request should NOT retry — it would just burn tokens.
    assert not _is_transient(FakeErr("invalid_request_error: bad tool schema"))


def _fake_trace(question: str, case_id: str, run_index: int, cost: float = 0.05) -> Trace:
    return Trace(
        run_id=str(uuid.uuid4()),
        case_id=case_id,
        run_index=run_index,
        question=question,
        model="claude-haiku-4-5",
        messages=[
            {"role": "user", "content": question},
            {"role": "assistant", "tool_calls": [{"id": "t", "name": "finish", "args": {"answer": "x", "citations": []}}], "latency_ms": 10},
        ],
        final_answer="x",
        citations=[],
        stopped_reason="finish",
        cost_usd=cost,
        wall_time_ms=10,
    )


@pytest.mark.asyncio
async def test_cost_governor_trips(tmp_path: Path):
    # Use any small case — the governor gates admission, not content.
    case = next(c for c in load_cases(Path("cases")) if c.id == "efficiency_no_extra_calls")
    # Ten runs, each $0.5 = $5.0; cap at $1.2 => at most 3 real runs admit.
    cases = [case]

    def factory(case_id: str, run_index: int):
        return lambda q: _fake_trace(q, case_id, run_index, cost=0.50)

    aggs = await run_suite(
        cases,
        traces_dir=tmp_path,
        concurrency=1,  # serialize so the governor observes spend in order
        repeats=10,
        agent_factory=factory,
        judge=StubJudge(),
        max_usd=1.20,
    )
    errs = [r for r in aggs[0].runs if r.error and "BudgetExceeded" in r.error]
    real = [r for r in aggs[0].runs if not (r.error and "BudgetExceeded" in r.error)]
    assert len(real) <= 3, f"expected ≤3 real runs under $1.20 cap, got {len(real)}"
    assert len(errs) >= 7, f"expected ≥7 skipped runs, got {len(errs)}"
