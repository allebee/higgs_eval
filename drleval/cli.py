"""Command-line interface.

    drleval run        — run the full suite against the agent
    drleval rescore    — re-score committed fixture traces (judge still runs)
    drleval diff       — diff two reports
    drleval view       — print the HTML report path

The tests target this with offline stubs; end-to-end use requires an API key.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from .agent_adapter import load_trace
from .loader import load_cases
from .reporter import aggregate_stats, build_report, diff_reports, write_report
from .runner import rescore_from_traces, run_suite_sync
from .viewer import render_html


def _collect_trace_messages(traces_dir: Path) -> dict[tuple[str, int], list[dict]]:
    out: dict[tuple[str, int], list[dict]] = {}
    for p in traces_dir.glob("*.json"):
        try:
            t = load_trace(p)
        except Exception:
            continue
        out[(t.case_id, t.run_index)] = t.messages
    return out


def cmd_run(args: argparse.Namespace) -> int:
    load_dotenv()
    cases_dir = Path(args.cases)
    out_dir = Path(args.out)
    traces_dir = Path(args.traces or out_dir / "traces")
    cases = load_cases(cases_dir)
    if args.filter:
        cases = [c for c in cases if args.filter in c.id]
    if not cases:
        print(f"no cases matched in {cases_dir}", file=sys.stderr)
        return 2
    print(f"running {len(cases)} cases × {args.repeats or 'per-case'} repeats, concurrency={args.concurrency}")

    t0 = time.time()
    aggregates = run_suite_sync(
        cases,
        traces_dir=traces_dir,
        concurrency=args.concurrency,
        repeats=args.repeats,
        max_usd=args.max_usd,
    )
    duration_ms = int((time.time() - t0) * 1000)

    report = build_report(
        aggregates,
        agent_model=os.getenv("DRL_MODEL", "claude-haiku-4-5"),
        judge_model=os.getenv("DRLEVAL_JUDGE_MODEL", "claude-haiku-4-5"),
        duration_ms=duration_ms,
    )
    json_path, _ = write_report(report, out_dir)
    _render_and_print(json_path, out_dir, traces_dir)
    return 0


def cmd_rescore(args: argparse.Namespace) -> int:
    load_dotenv()
    cases = load_cases(Path(args.cases))
    traces_dir = Path(args.traces)
    judge = None
    if args.no_judge:
        # Skip soft assertions entirely — hard checks still run. Useful for
        # offline grading without an API key.
        for c in cases:
            c.expected_behavior.soft = []
    aggregates = rescore_from_traces(cases, traces_dir, judge=judge)
    report = build_report(
        aggregates,
        agent_model=os.getenv("DRL_MODEL", "claude-haiku-4-5"),
        judge_model=os.getenv("DRLEVAL_JUDGE_MODEL", "claude-haiku-4-5"),
        duration_ms=0,
    )
    out_dir = Path(args.out)
    json_path, _ = write_report(report, out_dir)
    _render_and_print(json_path, out_dir, traces_dir)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    cur = json.loads(Path(args.current).read_text())
    prev = json.loads(Path(args.previous).read_text()) if Path(args.previous).exists() else None
    d = diff_reports(cur, prev)
    print(json.dumps(d.__dict__, indent=2))
    return 0 if not d.regressions else 1


def cmd_view(args: argparse.Namespace) -> int:
    p = Path(args.report)
    if not p.exists():
        print(f"no report at {p}", file=sys.stderr)
        return 2
    print(p.resolve())
    return 0


def _render_and_print(json_path: Path, out_dir: Path, traces_dir: Path) -> None:
    report = json.loads(json_path.read_text())
    prev = out_dir / "previous.json"
    prev_obj = json.loads(prev.read_text()) if prev.exists() else None
    diff = diff_reports(report, prev_obj) if prev_obj else None
    html_path = out_dir / "latest.html"
    render_html(
        report,
        diff=diff.__dict__ if diff else None,
        trace_messages_by_run=_collect_trace_messages(traces_dir),
        out_path=html_path,
    )
    agg = report["aggregate"]
    print(
        f"pass_rate={agg['pass_rate']*100:.1f}% "
        f"cost=${agg['total_cost_usd']:.4f} "
        f"p50={agg['p50_latency_ms']}ms p95={agg['p95_latency_ms']}ms "
        f"flaky={agg['cases_flaky']}"
    )
    if diff and diff.regressions:
        print(f"REGRESSIONS: {diff.regressions}")
    print(f"report -> {json_path}")
    print(f"viewer -> {html_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="drleval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run")
    p_run.add_argument("--cases", default="cases/")
    p_run.add_argument("--out", default="reports/")
    p_run.add_argument("--traces", default=None)
    p_run.add_argument("--concurrency", type=int, default=int(os.getenv("DRLEVAL_CONCURRENCY", "4")))
    p_run.add_argument("--repeats", type=int, default=None, help="override per-case repeats")
    p_run.add_argument("--filter", default=None, help="substring match on case id")
    p_run.add_argument(
        "--max-usd",
        type=float,
        default=float(os.getenv("DRLEVAL_MAX_USD", "0") or 0),
        help="abort admitting new runs once cumulative cost exceeds this (0 = no cap)",
    )
    p_run.set_defaults(func=cmd_run)

    p_re = sub.add_parser("rescore")
    p_re.add_argument("--cases", default="cases/")
    p_re.add_argument("--traces", default="fixtures/traces/")
    p_re.add_argument("--out", default="reports/")
    p_re.add_argument("--no-judge", action="store_true", help="skip LLM soft assertions (offline, hard-only)")
    p_re.set_defaults(func=cmd_rescore)

    p_diff = sub.add_parser("diff")
    p_diff.add_argument("--current", required=True)
    p_diff.add_argument("--previous", required=True)
    p_diff.set_defaults(func=cmd_diff)

    p_view = sub.add_parser("view")
    p_view.add_argument("--report", default="reports/latest.html")
    p_view.set_defaults(func=cmd_view)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
