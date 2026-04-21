"""Metric plugin registry.

Adding a metric:

    from drleval.metrics.registry import register
    @register("my_check", kind="hard")
    def my_check(trace, case, **kwargs): ...

No runner/scorer changes required.
"""
from __future__ import annotations

from typing import Any, Callable, Literal

from ..schema import Case, Trace, Verdict

MetricFn = Callable[..., Verdict]
METRICS: dict[str, tuple[Literal["hard", "soft"], MetricFn]] = {}


def register(name: str, *, kind: Literal["hard", "soft"]):
    def deco(fn: MetricFn) -> MetricFn:
        METRICS[name] = (kind, fn)
        return fn

    return deco


def dispatch(metric_name: str, trace: Trace, case: Case, /, **kwargs: Any) -> Verdict:
    """Dispatch via positional-only `metric_name` so metric kwargs may include
    a `name` key (e.g. `tool_called(name="web_search")`) without collision.
    """
    if metric_name not in METRICS:
        return Verdict(
            metric=metric_name,
            kind="hard",
            passed=False,
            rationale=f"Unknown metric {metric_name!r}. Registered: {sorted(METRICS)}",
        )
    kind, fn = METRICS[metric_name]
    try:
        v = fn(trace, case, **kwargs)
    except Exception as e:
        return Verdict(
            metric=metric_name,
            kind=kind,
            passed=False,
            rationale=f"Metric raised {type(e).__name__}: {e}",
        )
    if not v.metric:
        v.metric = metric_name
    v.kind = kind
    return v
