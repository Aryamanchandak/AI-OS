"""The Session 7 agent package.

Layout:
    agent.schemas              — typed data contracts (no local deps)
    agent.gateway              — LLM + embedding gateway bridge
    agent.cognition.*          — perception / decision / action / memory
    agent.services.*           — vector_index / artifacts
    agent.agent7               — orchestrator / entry point
    agent.app_planner          — FastAPI chat UI

Runtime state (FAISS index, memory.json, artifacts, upload sandbox) lives
under ``REPO_ROOT / "data"`` and is git-ignored.
"""

from __future__ import annotations

from pathlib import Path


def _find_repo_root() -> Path:
    """Return the repository root — the directory containing ``pyproject.toml``.

    Runtime data paths (``data/state``, ``data/sandbox``) derive from this so
    they resolve identically no matter which module or subprocess computes
    them. Walking up to ``pyproject.toml`` avoids the ``parents[N]`` counting
    that made the old layout fragile — the exact anti-pattern the restructure
    removed from ``gateway.py``.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(
        f"Could not locate the repo root: no ancestor of {here} contains "
        "pyproject.toml."
    )


REPO_ROOT = _find_repo_root()
DATA_DIR = REPO_ROOT / "data"
STATE_DIR = DATA_DIR / "state"
SANDBOX_DIR = DATA_DIR / "sandbox"

__all__ = ["REPO_ROOT", "DATA_DIR", "STATE_DIR", "SANDBOX_DIR"]
