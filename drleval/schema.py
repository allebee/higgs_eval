"""Pydantic data models — the contract between runner, scorer, reporter, viewer.

A `Trace` is the canonical record of one agent run. Scoring is a pure function
of (Case, Trace), which is what makes `rescore` possible without re-calling the
agent.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Assertions (per-case expected behavior) --------------------------------


class HardAssertion(BaseModel):
    """Deterministic check over the trace. Registered metric by `type`."""

    type: str
    # Free-form kwargs consumed by the registered metric function.
    model_config = {"extra": "allow"}


class SoftAssertion(BaseModel):
    """LLM-as-judge check. `rubric` is the stem of a file in rubrics/."""

    type: Literal["llm_judge"] = "llm_judge"
    rubric: str
    # Optional claims that must be present/absent in the answer. The judge sees
    # these as additional rubric context.
    must_contain_claim: str | None = None
    must_not_contain_claim: str | None = None
    # Propagate other kwargs to the judge prompt.
    model_config = {"extra": "allow"}


class ExpectedBehavior(BaseModel):
    hard: list[HardAssertion] = Field(default_factory=list)
    soft: list[SoftAssertion] = Field(default_factory=list)


class Case(BaseModel):
    id: str
    input: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    expected_behavior: ExpectedBehavior = Field(default_factory=ExpectedBehavior)
    repeats: int = 1


# --- Trace ------------------------------------------------------------------


class Trace(BaseModel):
    """Extends the shipped trace format with eval-framework metadata."""

    run_id: str
    case_id: str
    run_index: int = 0
    question: str
    model: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    final_answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    stopped_reason: str = "error"
    total_tokens: dict[str, int] = Field(default_factory=lambda: {"input": 0, "output": 0})
    cost_usd: float = 0.0
    wall_time_ms: int = 0
    error: str | None = None

    def tool_calls(self, name: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in self.messages:
            if m.get("role") != "assistant":
                continue
            for tc in m.get("tool_calls", []) or []:
                if name is None or tc.get("name") == name:
                    out.append(tc)
        return out

    def tool_results(self, name: str | None = None) -> list[dict[str, Any]]:
        return [
            m
            for m in self.messages
            if m.get("role") == "tool" and (name is None or m.get("name") == name)
        ]

    def step_count(self) -> int:
        return sum(1 for m in self.messages if m.get("role") == "assistant")

    def hash(self) -> str:
        canon = json.dumps(
            {
                "case_id": self.case_id,
                "question": self.question,
                "messages": self.messages,
                "final_answer": self.final_answer,
                "citations": self.citations,
                "stopped_reason": self.stopped_reason,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canon.encode()).hexdigest()[:16]


# --- Verdicts ---------------------------------------------------------------


class Verdict(BaseModel):
    metric: str
    kind: Literal["hard", "soft"]
    passed: bool
    rationale: str = ""
    evidence: list[str] = Field(default_factory=list)
    confidence: float | None = None
    cost_usd: float = 0.0


class CaseRunResult(BaseModel):
    """One (case, run_index) result."""

    case_id: str
    run_index: int
    trace_path: str | None = None
    trace_hash: str
    verdicts: list[Verdict] = Field(default_factory=list)
    passed: bool = False
    wall_time_ms: int = 0
    cost_usd: float = 0.0
    tool_call_count: int = 0
    stopped_reason: str = ""
    error: str | None = None

    def fail_reasons(self) -> list[str]:
        return [f"{v.metric}: {v.rationale or 'failed'}" for v in self.verdicts if not v.passed]


class CaseAggregate(BaseModel):
    """Aggregate of N repeats for one case."""

    case_id: str
    runs: list[CaseRunResult]

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.runs if r.passed)

    @property
    def pass_rate(self) -> float:
        return self.pass_count / len(self.runs) if self.runs else 0.0

    @property
    def flaky(self) -> bool:
        return 0 < self.pass_count < len(self.runs)


class RunReport(BaseModel):
    run_id: str
    started_at: str
    duration_ms: int
    agent_model: str
    judge_model: str
    cases: list[CaseAggregate]

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for c in self.cases for r in c.runs)

    @property
    def total_runs(self) -> int:
        return sum(len(c.runs) for c in self.cases)

    @property
    def pass_rate(self) -> float:
        passed = sum(1 for c in self.cases for r in c.runs if r.passed)
        return passed / self.total_runs if self.total_runs else 0.0
