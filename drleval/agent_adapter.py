"""Adapts the shipped `agent.py` into a Trace the framework understands.

The framework treats the agent as a pure callable `question -> Trace`. This
module wraps `run_agent` from the shipped agent so we never have to modify it.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Callable

from .schema import Trace

# Make the repo root importable so `import agent, tools` works when drleval
# is installed or invoked from elsewhere.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


AgentCallable = Callable[[str], Trace]


def default_agent(case_id: str, run_index: int) -> AgentCallable:
    """Return a callable that runs the real agent and wraps its output."""
    from agent import run_agent  # local import: only needed when actually running

    def _call(question: str) -> Trace:
        t0 = time.time()
        result = run_agent(question)
        trace = Trace(
            run_id=result.run_id,
            case_id=case_id,
            run_index=run_index,
            question=question,
            model=result.model,
            messages=result.messages,
            final_answer=result.final_answer,
            citations=result.citations,
            stopped_reason=result.stopped_reason,
            total_tokens=result.total_tokens,
            cost_usd=result.cost_usd,
            wall_time_ms=result.wall_time_ms or int((time.time() - t0) * 1000),
            error=result.error,
        )
        return trace

    return _call


def save_trace(trace: Trace, traces_dir: Path) -> Path:
    traces_dir.mkdir(parents=True, exist_ok=True)
    path = traces_dir / f"{trace.case_id}__{trace.run_index}__{trace.run_id}.json"
    with path.open("w") as f:
        json.dump(trace.model_dump(), f, indent=2, default=str)
    return path


def load_trace(path: Path) -> Trace:
    data = json.loads(path.read_text())
    return Trace(**data)
