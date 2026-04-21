"""LLM-as-judge soft assertion. Thin wrapper; all logic lives in judge.py."""
from __future__ import annotations

from typing import Any

from ..judge import get_judge
from ..schema import Case, Trace, Verdict
from .registry import register


# Rubrics that benefit from seeing the fetched page text as authoritative
# ground truth. Everything else either doesn't need it or would be biased by
# its presence (refusal/injection checks are about behavior, not content).
_PAGE_AWARE_RUBRICS = {"quote_grounded", "factual_correctness"}


def _fetched_pages(trace: Trace) -> dict[str, str]:
    """Pair each fetch_url call to its tool_result content."""
    out: dict[str, str] = {}
    pending: dict[str, str] = {}
    for m in trace.messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                if tc.get("name") == "fetch_url":
                    url = (tc.get("args") or {}).get("url")
                    if url:
                        pending[tc.get("id", "")] = url
        elif m.get("role") == "tool" and m.get("name") == "fetch_url":
            url = pending.pop(m.get("tool_use_id", ""), None)
            if url is None:
                continue
            content = m.get("content")
            if isinstance(content, str):
                out[url] = content
    return out


@register("llm_judge", kind="soft")
def llm_judge(
    trace: Trace,
    case: Case,
    *,
    rubric: str,
    must_contain_claim: str | None = None,
    must_not_contain_claim: str | None = None,
    judge: Any = None,
    **_: Any,
) -> Verdict:
    j = judge or get_judge()
    extra: dict[str, Any] = {}
    if must_contain_claim:
        extra["must_contain_claim"] = must_contain_claim
    if must_not_contain_claim:
        extra["must_not_contain_claim"] = must_not_contain_claim

    pages = _fetched_pages(trace) if rubric in _PAGE_AWARE_RUBRICS else None

    out = j.evaluate(
        rubric_name=rubric,
        question=trace.question,
        final_answer=trace.final_answer or "",
        citations=trace.citations,
        extra_context=extra or None,
        fetched_pages=pages,
    )
    verdict = out.get("verdict", "fail")
    return Verdict(
        metric=f"llm_judge:{rubric}",
        kind="soft",
        # `partial` counts as failure for pass-rate math but is reported honestly
        # in rationale so reviewers can see degree of failure.
        passed=(verdict == "pass"),
        rationale=f"[{verdict}] {out.get('rationale', '')}",
        evidence=list(out.get("evidence") or []),
        confidence=float(out.get("confidence") or 0.0),
        cost_usd=float(out.get("cost_usd") or 0.0),
    )
