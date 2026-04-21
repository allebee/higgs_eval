"""Runner + scorer + reporter + diff tests with a fake agent (no API)."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import pytest

from drleval.judge import StubJudge
from drleval.loader import load_cases
from drleval.reporter import aggregate_stats, build_report, diff_reports, write_report
from drleval.runner import run_suite
from drleval.schema import Trace


def _fake_trace_for(question: str, case_id: str, run_index: int, *, hallucinate: bool = False) -> Trace:
    citations = ["https://corpus.local/voyager-timeline"]
    fetched_url = citations[0]
    quotes_content = [
        "Voyager 1 crossed the heliopause in August 2012"
        if not hallucinate
        else "Voyager 1 was the first spacecraft ever to reach interstellar territory",
    ]
    return Trace(
        run_id=str(uuid.uuid4()),
        case_id=case_id,
        run_index=run_index,
        question=question,
        model="claude-haiku-4-5",
        messages=[
            {"role": "user", "content": question},
            {"role": "assistant", "tool_calls": [{"name": "web_search", "args": {"query": question}}], "latency_ms": 10},
            {"role": "tool", "name": "web_search", "content": [{"url": fetched_url, "title": "t", "snippet": "s"}], "latency_ms": 1},
            {"role": "assistant", "tool_calls": [{"name": "fetch_url", "args": {"url": fetched_url}}], "latency_ms": 10},
            {"role": "tool", "name": "fetch_url", "content": "Voyager 1 crossed the heliopause in August 2012, becoming the first human-made object to enter interstellar space.", "latency_ms": 1},
            {"role": "assistant", "tool_calls": [{"id": "eq1", "name": "extract_quotes", "args": {"text": "Voyager 1 crossed the heliopause in August 2012, becoming the first human-made object to enter interstellar space.", "topic": "heliopause"}}], "latency_ms": 10},
            {"role": "tool", "name": "extract_quotes", "tool_use_id": "eq1", "content": quotes_content, "latency_ms": 1},
            {"role": "assistant", "tool_calls": [{"name": "finish", "args": {"answer": "Voyager 1 crossed the heliopause in August 2012.", "citations": citations}}], "latency_ms": 10},
        ],
        final_answer="Voyager 1 crossed the heliopause in August 2012.",
        citations=citations,
        stopped_reason="finish",
        total_tokens={"input": 100, "output": 50},
        cost_usd=0.001,
        wall_time_ms=50,
    )


@pytest.mark.asyncio
async def test_runner_with_fake_agent(tmp_path: Path):
    cases = [c for c in load_cases(Path("cases")) if c.id == "happy_voyager1_heliopause"]
    assert cases, "happy_voyager1_heliopause case must exist"

    def factory(case_id: str, run_index: int):
        return lambda q: _fake_trace_for(q, case_id, run_index)

    aggs = await run_suite(
        cases,
        traces_dir=tmp_path / "traces",
        concurrency=2,
        agent_factory=factory,
        judge=StubJudge(),
    )
    assert aggs[0].pass_count == 1
    assert aggs[0].runs[0].passed


@pytest.mark.asyncio
async def test_runner_surfaces_hallucinated_quotes(tmp_path: Path):
    cases = [c for c in load_cases(Path("cases")) if c.id == "quote_faithfulness_check"]
    assert cases

    def factory(case_id: str, run_index: int):
        return lambda q: _fake_trace_for(q, case_id, run_index, hallucinate=True)

    aggs = await run_suite(
        cases,
        traces_dir=tmp_path / "traces",
        concurrency=2,
        repeats=1,
        agent_factory=factory,
        judge=StubJudge(),
    )
    run = aggs[0].runs[0]
    assert not run.passed, "hallucinated quotes should fail the faithfulness case"
    fail_metrics = [v.metric for v in run.verdicts if not v.passed]
    assert "quotes_substring_grounded" in fail_metrics


def test_report_diff_flags_regressions(tmp_path: Path):
    prev = {
        "aggregate": {"pass_rate": 1.0, "total_cost_usd": 0.10},
        "cases": [{"case_id": "a", "runs": [{"passed": True}]}, {"case_id": "b", "runs": [{"passed": True}]}],
    }
    cur = {
        "aggregate": {"pass_rate": 0.5, "total_cost_usd": 0.15},
        "cases": [{"case_id": "a", "runs": [{"passed": True}]}, {"case_id": "b", "runs": [{"passed": False}]}],
    }
    d = diff_reports(cur, prev)
    assert d.regressions == ["b"]
    assert d.fixes == []
    assert d.pass_rate_delta == pytest.approx(-0.5)
