"""Bridge to the shared llm_gateway service.

This agent uses the gateway's chat endpoint plus `POST /v1/embed`.

Auto-starts the gateway on port 8107 if it is not already up, then
re-exports the gateway `LLM` client and a module-level `embed()` helper. Every
layer in this agent imports from here so the boot logic lives in one place.
"""

from __future__ import annotations

import os
import subprocess
import shutil
import time
from pathlib import Path

import httpx


def _find_workspace_root() -> Path:
    """Locate the 'AI Code' workspace root that holds the sibling services.

    The agent shells out to three siblings — ``llm_gateway``, ``mcp_server``,
    and the root ``.venv`` — so the root is defined by their presence, not by
    counting parent directories. Counting (the old ``parents[2]``) silently
    broke the moment this file changed depth; walking up to the siblings makes
    the anchor survive any future move. An ``AI_CODE_ROOT`` env var overrides.
    """
    env = os.environ.get("AI_CODE_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "llm_gateway").is_dir() and (parent / "mcp_server").is_dir():
            return parent
    raise RuntimeError(
        "Could not locate the AI Code workspace root: no ancestor of "
        f"{here} contains both 'llm_gateway' and 'mcp_server'. "
        "Set the AI_CODE_ROOT environment variable to point at it."
    )


AI_CODE_ROOT = _find_workspace_root()
GATEWAY_V7_DIR = AI_CODE_ROOT / "llm_gateway"
GATEWAY_URL = "http://localhost:8107"
ROOT_PYTHON = AI_CODE_ROOT / ".venv" / "bin" / "python"
GATEWAY_PYTHON = GATEWAY_V7_DIR / ".venv" / "bin" / "python"


def _gateway_command() -> list[str]:
    if GATEWAY_PYTHON.exists():
        return [str(GATEWAY_PYTHON), "main.py"]
    if shutil.which("uv"):
        return ["uv", "run", "python", "main.py"]
    return [str(ROOT_PYTHON), "main.py"]


def _is_up() -> bool:
    try:
        httpx.get(f"{GATEWAY_URL}/v1/providers", timeout=2.0)
        return True
    except Exception:
        return False


def ensure_gateway() -> None:
    """Start the gateway if it is not already running. Idempotent."""
    if _is_up():
        return
    if not GATEWAY_V7_DIR.exists():
        raise RuntimeError(
            f"Gateway directory not found at {GATEWAY_V7_DIR}. "
            "Confirm the shared llm_gateway folder exists before running the agent."
        )
    log_path = GATEWAY_V7_DIR / "gateway.log"
    print(f"[gateway] launching llm_gateway from {GATEWAY_V7_DIR} (log → {log_path})")
    log_file = open(log_path, "a")
    subprocess.Popen(
        _gateway_command(),
        cwd=str(GATEWAY_V7_DIR),
        stdout=log_file,
        stderr=log_file,
    )
    for _ in range(45):
        time.sleep(1)
        if _is_up():
            print(f"[gateway] up on {GATEWAY_URL}")
            return
    raise RuntimeError(f"Gateway failed to start within 45s. Check {GATEWAY_V7_DIR}")


# Load the gateway's client.py without polluting sys.path. The gateway dir has its
# own `schemas.py`, which would shadow ours if we put it on the path.
import importlib.util as _importlib_util

_client_path = GATEWAY_V7_DIR / "client.py"
if _client_path.exists():
    _spec = _importlib_util.spec_from_file_location("llm_gateway_client", _client_path)
    _mod = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    LLM = _mod.LLM
else:
    LLM = None  # populated once V7 is built; importers should ensure_gateway() first


def embed(text: str, task_type: str = "retrieval_document") -> dict:
    """Compute an embedding for `text` via the gateway's V7 embed endpoint.

    Returns the full response dict: `{embedding, dim, model, provider,
    latency_ms, ...}`. The chosen embedding model is fixed at the gateway
    level. Changing it invalidates every FAISS index built against the old
    vectors, so callers should treat the model as a project-level constant.
    """
    ensure_gateway()
    if LLM is None:
        raise RuntimeError(
            "Gateway client unavailable. Confirm llm_gateway/client.py exists."
        )
    return LLM().embed(text, task_type=task_type)


__all__ = ["ensure_gateway", "LLM", "GATEWAY_URL", "GATEWAY_V7_DIR", "embed"]
