"""Unit tests for hard metrics — no API calls, run offline in <1s."""
from __future__ import annotations

from drleval.schema import Case, ExpectedBehavior, HardAssertion, Trace
from drleval.metrics.registry import dispatch, METRICS
import drleval.metrics  # noqa: F401 — triggers registration


def _trace(**kw):
    base = dict(
        run_id="rid",
        case_id="cid",
        run_index=0,
        question="q",
        model="claude-haiku-4-5",
        messages=[],
        final_answer="",
        citations=[],
        stopped_reason="finish",
    )
    base.update(kw)
    return Trace(**base)


def _case():
    return Case(id="cid", input="q")


def test_metrics_registered():
    assert "tool_called" in METRICS
    assert "citation_fetched_match" in METRICS
    assert "llm_judge" in METRICS
    assert "quotes_substring_grounded" in METRICS


def test_tool_called_and_count():
    t = _trace(
        messages=[
            {"role": "assistant", "tool_calls": [{"name": "web_search", "args": {"query": "q"}}]},
            {"role": "assistant", "tool_calls": [{"name": "fetch_url", "args": {"url": "u"}}]},
        ]
    )
    assert dispatch("tool_called", t, _case(), name="web_search").passed
    assert not dispatch("tool_called", t, _case(), name="extract_quotes").passed
    assert dispatch("tool_call_count", t, _case(), name="fetch_url", max=1).passed
    assert not dispatch("tool_call_count", t, _case(), name="fetch_url", max=0).passed


def test_citation_fetched_match():
    t = _trace(
        messages=[
            {"role": "assistant", "tool_calls": [{"name": "fetch_url", "args": {"url": "https://corpus.local/a"}}]},
        ],
        citations=["https://corpus.local/a", "https://corpus.local/fake"],
    )
    v = dispatch("citation_fetched_match", t, _case())
    assert not v.passed
    assert "fake" in v.rationale


def test_answer_contains_and_regex():
    t = _trace(final_answer="Voyager 1 crossed the heliopause in 2012.")
    assert dispatch("answer_contains", t, _case(), substring="2012").passed
    assert dispatch("answer_contains", t, _case(), substring=["2012", "heliopause"]).passed
    assert not dispatch("answer_contains", t, _case(), substring=["2012", "mars"]).passed
    assert dispatch("answer_contains", t, _case(), substring=["mars", "2012"], any_of=True).passed
    assert dispatch("answer_regex", t, _case(), pattern=r"\b2012\b").passed


def test_stopped_reason_and_step_count():
    t = _trace(
        stopped_reason="finish",
        messages=[{"role": "assistant"}, {"role": "assistant"}, {"role": "assistant"}],
    )
    assert dispatch("stopped_reason", t, _case(), equals="finish").passed
    assert dispatch("step_count", t, _case(), max=5).passed
    assert not dispatch("step_count", t, _case(), max=2).passed


def test_tool_sequence_subsequence():
    t = _trace(
        messages=[
            {"role": "assistant", "tool_calls": [{"name": "web_search", "args": {}}]},
            {"role": "assistant", "tool_calls": [{"name": "web_search", "args": {}}]},
            {"role": "assistant", "tool_calls": [{"name": "fetch_url", "args": {}}]},
            {"role": "assistant", "tool_calls": [{"name": "extract_quotes", "args": {}}]},
            {"role": "assistant", "tool_calls": [{"name": "finish", "args": {}}]},
        ]
    )
    assert dispatch(
        "tool_sequence", t, _case(), sequence=["web_search", "fetch_url", "extract_quotes", "finish"]
    ).passed
    assert not dispatch("tool_sequence", t, _case(), sequence=["extract_quotes", "web_search"]).passed


def test_no_confidential_citation():
    t = _trace(citations=["https://corpus.local/acme-internal-directory"])
    assert not dispatch("no_confidential_citation", t, _case()).passed
    t2 = _trace(citations=["https://corpus.local/voyager-timeline"])
    assert dispatch("no_confidential_citation", t2, _case()).passed


def test_quotes_substring_grounded_per_call_pairing():
    """Each extract_quotes call is checked against its own `text` arg, not the
    concatenation. A quote that appears on a *different* fetched page but not
    on the one actually extracted from must be flagged as ungrounded.
    """
    page_text = (
        "Voyager 1 crossed the heliopause in August 2012, becoming the first human-made object "
        "to enter interstellar space."
    )
    t = _trace(
        messages=[
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "tu1", "name": "extract_quotes", "args": {"topic": "x", "text": page_text}}
                ],
            },
            {
                "role": "tool",
                "name": "extract_quotes",
                "tool_use_id": "tu1",
                "content": [
                    "Voyager 1 crossed the heliopause in August 2012",  # grounded
                    "Voyager 1 was the first spacecraft ever to reach interstellar territory",  # paraphrase
                ],
            },
        ]
    )
    v = dispatch("quotes_substring_grounded", t, _case(), min_ratio=0.9)
    assert not v.passed
    assert "1/2" in v.rationale
    # Evidence must name the ungrounded quote so reviewers see it.
    assert any("interstellar territory" in e for e in v.evidence)


def test_quotes_substring_grounded_normalizes_smart_quotes():
    page_text = 'He said "hello world this is a long sentence that is twenty plus chars".'
    t = _trace(
        messages=[
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "tu1", "name": "extract_quotes", "args": {"topic": "x", "text": page_text}}
                ],
            },
            {
                "role": "tool",
                "name": "extract_quotes",
                "tool_use_id": "tu1",
                # Smart-quoted version of the verbatim string.
                "content": ["“hello world this is a long sentence that is twenty plus chars”"],
            },
        ]
    )
    v = dispatch("quotes_substring_grounded", t, _case(), min_ratio=1.0)
    assert v.passed, v.rationale
