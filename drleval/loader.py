"""YAML case loader."""
from __future__ import annotations

from pathlib import Path

import yaml

from .schema import Case, ExpectedBehavior, HardAssertion, SoftAssertion


def load_case(path: Path) -> Case:
    raw = yaml.safe_load(path.read_text())
    eb_raw = raw.get("expected_behavior") or {}
    eb = ExpectedBehavior(
        hard=[HardAssertion(**a) for a in eb_raw.get("hard", [])],
        soft=[SoftAssertion(**a) for a in eb_raw.get("soft", [])],
    )
    return Case(
        id=raw.get("id") or path.stem,
        input=raw["input"],
        description=raw.get("description"),
        tags=raw.get("tags", []),
        expected_behavior=eb,
        repeats=int(raw.get("repeats", 1)),
    )


def load_cases(cases_dir: Path, pattern: str = "*.yaml") -> list[Case]:
    paths = sorted(cases_dir.glob(pattern)) + sorted(cases_dir.glob("*.yml"))
    seen: set[str] = set()
    out: list[Case] = []
    for p in paths:
        if p.name in seen:
            continue
        seen.add(p.name)
        out.append(load_case(p))
    return out
