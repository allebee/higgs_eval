"""Verify the soft metric passes fetched page text to the judge for
page-aware rubrics, and does NOT for behavior-only rubrics.
"""
from __future__ import annotations

from drleval.judge import StubJudge
from drleval.metrics.registry import dispatch
from drleval.schema import Case, Trace


def _trace_with_fetch():
    return Trace(
        run_id="r",
        case_id="c",
        run_index=0,
        question="q",
        model="m",
        messages=[
            {
                "role": "assistant",
                "tool_calls": [{"id": "tu1", "name": "fetch_url", "args": {"url": "https://ex/a"}}],
            },
            {"role": "tool", "name": "fetch_url", "tool_use_id": "tu1", "content": "PAGE A BODY"},
            {
                "role": "assistant",
                "tool_calls": [{"id": "tu2", "name": "fetch_url", "args": {"url": "https://ex/b"}}],
            },
            {"role": "tool", "name": "fetch_url", "tool_use_id": "tu2", "content": "PAGE B BODY"},
        ],
        final_answer="ans",
        citations=["https://ex/a"],
        stopped_reason="finish",
    )


def test_page_aware_rubric_gets_fetched_pages():
    j = StubJudge()
    dispatch("llm_judge", _trace_with_fetch(), Case(id="c", input="q"), rubric="quote_grounded", judge=j)
    pages = j.last_call.get("fetched_pages")
    assert pages == {"https://ex/a": "PAGE A BODY", "https://ex/b": "PAGE B BODY"}


def test_behavior_only_rubric_does_not_get_pages():
    j = StubJudge()
    dispatch("llm_judge", _trace_with_fetch(), Case(id="c", input="q"), rubric="refusal_correctness", judge=j)
    assert j.last_call.get("fetched_pages") is None
