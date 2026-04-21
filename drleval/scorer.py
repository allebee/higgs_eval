"""Pure scoring: (Case, Trace) -> CaseRunResult.

Does not call the agent. Judge calls happen here (they are independent of the
agent, so scoring from cached traces still incurs judge cost).
"""
from __future__ import annotations

from typing import Any

# Ensure metrics are registered.
from . import metrics as _metrics  # noqa: F401
from .metrics.registry import dispatch
from .schema import Case, CaseRunResult, Trace, Verdict


def score(case: Case, trace: Trace, *, judge: Any = None) -> CaseRunResult:
    verdicts: list[Verdict] = []

    for hard in case.expected_behavior.hard:
        kwargs = hard.model_dump()
        name = kwargs.pop("type")
        verdicts.append(dispatch(name, trace, case, **kwargs))

    for soft in case.expected_behavior.soft:
        kwargs = soft.model_dump()
        name = kwargs.pop("type")
        # Let metrics accept `judge=` for test injection without polluting YAML.
        verdicts.append(dispatch(name, trace, case, judge=judge, **kwargs))

    total_cost = (trace.cost_usd or 0.0) + sum(v.cost_usd for v in verdicts)
    return CaseRunResult(
        case_id=case.id,
        run_index=trace.run_index,
        trace_hash=trace.hash(),
        verdicts=verdicts,
        passed=all(v.passed for v in verdicts) if verdicts else False,
        wall_time_ms=trace.wall_time_ms,
        cost_usd=total_cost,
        tool_call_count=len(trace.tool_calls()),
        stopped_reason=trace.stopped_reason,
        error=trace.error,
    )
