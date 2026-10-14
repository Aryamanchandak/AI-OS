"""Small FastAPI frontend for the hand-built ReAct loop."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .brain import OpenAIBrain
from .config import LoopConfig
from .logging_setup import configure_logging
from .loop import LoopResult, ReactLoop
from .mcp_client import MCPClient

RunTask = Callable[[str], Awaitable[LoopResult]]

_ROOT = Path(__file__).resolve().parent.parent
_STATIC_DIR = _ROOT / "frontend" / "static"

configure_logging()

app = FastAPI(title="React Loop Web")
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

_session: dict[str, Any] = {"runs": []}


class RunRequest(BaseModel):
    task: str = Field(min_length=1, max_length=8000)


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/ui/latest", response_class=HTMLResponse)
async def latest_ui() -> HTMLResponse:
    """Serve the most recent UI the agent built with the render_ui tool.

    render_ui runs in the MCP subprocess and writes an HTML snapshot to the
    shared file store; this route reads that snapshot back. The agent composes
    the Prefab tree itself — this is the only UI surface it communicates through.
    """
    import filestore  # lazy: keeps web import light

    snapshot = filestore.base_dir() / "generated_ui" / "index.html"
    if not snapshot.exists():
        raise HTTPException(
            status_code=404,
            detail="No UI has been generated yet. Ask the agent to build one.",
        )
    return HTMLResponse(snapshot.read_text(encoding="utf-8"))


@app.get("/api/state")
async def state() -> dict[str, Any]:
    return {"runs": _session["runs"]}


@app.post("/api/new_session")
async def new_session() -> dict[str, Any]:
    _session["runs"] = []
    return {"runs": []}


@app.get("/api/podcasts")
async def podcasts() -> dict[str, Any]:
    """Curated podcast feeds for the composer's dropdown (name -> RSS URL)."""
    from podcast_tools.feeds import list_feeds  # lazy: keeps web import light

    return {"podcasts": list_feeds()}


@app.get("/api/tools")
async def tools() -> dict[str, Any]:
    try:
        cfg = LoopConfig.from_env()
        async with MCPClient(cfg.server) as client:
            found = await client.list_tools()
    except Exception as e:  # noqa: BLE001 - surface startup/config failures.
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "tools": [
            {"name": t.name, "description": (t.description or "").strip()}
            for t in found
        ]
    }


@app.post("/api/run")
async def run(req: RunRequest) -> dict[str, Any]:
    task = req.task.strip()
    if not task:
        raise HTTPException(status_code=422, detail="Task cannot be blank.")

    runner: RunTask = getattr(app.state, "run_task", _run_task)
    try:
        result = await runner(task)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 - send actionable UI error.
        raise HTTPException(status_code=500, detail=str(e)) from e

    payload = _result_payload(task, result)
    _session["runs"].append(payload)
    _session["runs"] = _session["runs"][-20:]
    return payload


async def _run_task(task: str) -> LoopResult:
    cfg = LoopConfig.from_env()
    if not cfg.api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to the shared workspace .env "
            "or this project's environment, then retry."
        )

    brain = OpenAIBrain(model=cfg.model, api_key=cfg.api_key)
    async with MCPClient(cfg.server) as client:
        loop = ReactLoop(brain, client, cfg)
        return await loop.run(task)


def _result_payload(task: str, result: LoopResult) -> dict[str, Any]:
    return {
        "task": task,
        "final_answer": result.final_answer,
        "stop_reason": result.stop_reason,
        "trajectory": [entry.to_dict() for entry in result.trajectory.entries],
    }
