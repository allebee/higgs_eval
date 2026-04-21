"""Report builder: JSON + aggregate stats + diff vs previous."""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import CaseAggregate, RunReport


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return xs[k]


def wilson_ci(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial pass rate.

    Better-behaved than normal approximation at small N — which is the regime
    we're always in (3-10 repeats). Returns (lo, hi) in [0, 1].
    """
    if total == 0:
        return (0.0, 0.0)
    p = passed / total
    denom = 1 + z * z / total
    center = p + z * z / (2 * total)
    margin = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5)
    lo = max(0.0, (center - margin) / denom)
    hi = min(1.0, (center + margin) / denom)
    return (lo, hi)


def aggregate_stats(cases: list[CaseAggregate]) -> dict[str, Any]:
    latencies = [r.wall_time_ms for c in cases for r in c.runs]
    tool_calls = [r.tool_call_count for c in cases for r in c.runs]
    total_runs = sum(len(c.runs) for c in cases)
    passed_runs = sum(1 for c in cases for r in c.runs if r.passed)
    total_cost = sum(r.cost_usd for c in cases for r in c.runs)

    lo, hi = wilson_ci(passed_runs, total_runs)
    return {
        "pass_rate": passed_runs / total_runs if total_runs else 0.0,
        "pass_rate_ci95": [round(lo, 4), round(hi, 4)],
        "cases_passed": sum(1 for c in cases if c.pass_count == len(c.runs) and c.runs),
        "cases_failed": sum(1 for c in cases if c.pass_count == 0),
        "cases_flaky": sum(1 for c in cases if c.flaky),
        "total_runs": total_runs,
        "passed_runs": passed_runs,
        "total_cost_usd": round(total_cost, 4),
        "p50_latency_ms": int(_pct(latencies, 50)),
        "p95_latency_ms": int(_pct(latencies, 95)),
        "mean_tool_calls": round(statistics.fmean(tool_calls), 2) if tool_calls else 0.0,
    }


def build_report(
    cases: list[CaseAggregate],
    *,
    agent_model: str,
    judge_model: str,
    duration_ms: int,
) -> RunReport:
    import uuid

    return RunReport(
        run_id=str(uuid.uuid4()),
        started_at=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
        agent_model=agent_model,
        judge_model=judge_model,
        cases=cases,
    )


def write_report(report: RunReport, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "latest.json"
    # Rotate previous if it exists.
    if json_path.exists():
        (out_dir / "previous.json").write_text(json_path.read_text())
    data = report.model_dump()
    data["aggregate"] = aggregate_stats(report.cases)
    # Per-metric variance for each case — required by task when repeats > 1.
    # Always emitted (trivially N=1 when no repeats) so the shape is stable.
    for i, c in enumerate(report.cases):
        data["cases"][i]["metric_variance"] = c.metric_variance()
    json_path.write_text(json.dumps(data, indent=2, default=str))
    return json_path, out_dir


# --- Diff -------------------------------------------------------------------


@dataclass
class Diff:
    regressions: list[str]  # case ids that went pass->fail (any run)
    fixes: list[str]        # case ids that went fail->pass
    new: list[str]
    removed: list[str]
    pass_rate_delta: float
    cost_delta: float


def diff_reports(current: dict[str, Any], previous: dict[str, Any] | None) -> Diff:
    if not previous:
        return Diff([], [], [c["case_id"] for c in current["cases"]], [], 0.0, 0.0)

    def _summary(cases: list[dict[str, Any]]) -> dict[str, float]:
        return {
            c["case_id"]: (sum(1 for r in c["runs"] if r["passed"]) / max(len(c["runs"]), 1))
            for c in cases
        }

    prev_map = _summary(previous["cases"])
    cur_map = _summary(current["cases"])

    regressions = sorted([k for k in cur_map if k in prev_map and prev_map[k] > cur_map[k]])
    fixes = sorted([k for k in cur_map if k in prev_map and prev_map[k] < cur_map[k]])
    new = sorted([k for k in cur_map if k not in prev_map])
    removed = sorted([k for k in prev_map if k not in cur_map])

    pr_delta = current["aggregate"]["pass_rate"] - previous.get("aggregate", {}).get("pass_rate", 0.0)
    cost_delta = current["aggregate"]["total_cost_usd"] - previous.get("aggregate", {}).get("total_cost_usd", 0.0)
    return Diff(regressions, fixes, new, removed, pr_delta, cost_delta)
