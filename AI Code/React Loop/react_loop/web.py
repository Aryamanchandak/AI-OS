"""Small FastAPI frontend for the hand-built ReAct loop."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .brain import OpenAIBrain
from .config import LoopConfig
from .logging_setup import configure_logging
from .loop import LoopResult, ReactLoop
from .mcp_client import MCPClient
from .trace import TraceEntry, Trajectory

RunTask = Callable[[str], Awaitable[LoopResult]]
RunLoop = Callable[[str, "Callable[[TraceEntry], None] | None"], Awaitable[LoopResult]]

_ROOT = Path(__file__).resolve().parent.parent
_STATIC_DIR = _ROOT / "frontend" / "static"

# Tools that publish a UI snapshot; matched against the trajectory to decide
# whether a run produced one worth persisting (see _persist_ui_snapshot).
_UI_TOOLS = {"render_ui", "render_ui_from_json"}
_RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")

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


@app.get("/ui/runs/{run_id}")
async def run_ui(run_id: str) -> FileResponse:
    """Serve the UI snapshot a *specific* run generated (see _persist_ui_snapshot).

    Unlike /ui/latest, this is durable per run: switching between runs in the
    sidebar shows the UI that run actually built, not whatever render_ui call
    happened most recently across the whole session.
    """
    import filestore  # lazy: keeps web import light

    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=404, detail="No UI was generated for this run.")

    snapshot = filestore.base_dir() / "generated_ui" / "runs" / f"{run_id}.html"
    if not snapshot.exists():
        raise HTTPException(status_code=404, detail="No UI was generated for this run.")
    # FileResponse streams from disk rather than buffering the whole snapshot
    # in memory — matters once bundled-renderer snapshots run a few MB each.
    return FileResponse(str(snapshot), media_type="text/html")


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

    payload = _result_payload(task, result, uuid.uuid4().hex[:12])
    _session["runs"].append(payload)
    _session["runs"] = _session["runs"][-20:]
    return payload


@app.post("/api/run/stream")
async def run_stream(req: RunRequest) -> StreamingResponse:
    """Like /api/run, but streams each trajectory step as it happens.

    A run that self-corrects a bad render_ui snippet or runs a multi-step
    podcast pipeline can take a while; /api/run gives no feedback until the
    whole loop finishes. This wires the loop's existing (previously unused)
    `on_entry` hook to a queue and yields one NDJSON line per event:
    `{"type": "step", "entry": {...}}` as steps happen, then one
    `{"type": "final", ...}` line shaped like /api/run's response, or
    `{"type": "error", "detail": ...}` on failure. /api/run itself is
    untouched — this is additive, not a replacement.
    """
    task = req.task.strip()
    if not task:
        raise HTTPException(status_code=422, detail="Task cannot be blank.")

    return StreamingResponse(_stream_run(task), media_type="application/x-ndjson")


async def _stream_run(task: str):
    queue: asyncio.Queue = asyncio.Queue()

    def on_entry(entry: TraceEntry) -> None:
        queue.put_nowait(("entry", entry))

    async def drive() -> None:
        try:
            # Same injection seam as /api/run's app.state.run_task, so tests
            # can drive this without a real brain/MCP client/API key.
            runner: RunLoop = getattr(app.state, "run_loop", _run_loop)
            result = await runner(task, on_entry)
            await queue.put(("done", result))
        except Exception as e:  # noqa: BLE001 - surfaced as an error line, not a crash
            await queue.put(("error", str(e)))

    driver = asyncio.create_task(drive())
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "entry":
                yield json.dumps({"type": "step", "entry": payload.to_dict()}) + "\n"
            elif kind == "done":
                final = _result_payload(task, payload, uuid.uuid4().hex[:12])
                _session["runs"].append(final)
                _session["runs"] = _session["runs"][-20:]
                yield json.dumps({"type": "final", **final}) + "\n"
                break
            else:  # "error"
                yield json.dumps({"type": "error", "detail": payload}) + "\n"
                break
    finally:
        await driver


async def _run_loop(
    task: str, on_entry: Callable[[TraceEntry], None] | None = None
) -> LoopResult:
    cfg = LoopConfig.from_env()
    if not cfg.api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to the shared workspace .env "
            "or this project's environment, then retry."
        )

    brain = OpenAIBrain(model=cfg.model, api_key=cfg.api_key)
    async with MCPClient(cfg.server) as client:
        loop = ReactLoop(brain, client, cfg, on_entry=on_entry)
        return await loop.run(task)


async def _run_task(task: str) -> LoopResult:
    return await _run_loop(task)


def _persist_ui_snapshot(run_id: str, trajectory: Trajectory) -> str | None:
    """Copy the just-written global UI snapshot into a durable per-run file.

    render_ui/render_ui_from_json always overwrite one global snapshot
    (served at /ui/latest above); this makes *this run's* UI durable so
    switching between runs in the sidebar shows the right one instead of
    whichever run rendered a UI most recently.
    """
    produced = any(
        entry.tool in _UI_TOOLS
        and entry.observation
        and "rendered successfully" in entry.observation
        for entry in trajectory.entries
    )
    if not produced:
        return None

    import filestore  # lazy: keeps web import light

    src = filestore.base_dir() / "generated_ui" / "index.html"
    if not src.exists():
        return None

    dest_dir = filestore.base_dir() / "generated_ui" / "runs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{run_id}.html"
    shutil.copyfile(src, dest)
    return f"/ui/runs/{run_id}"


def _result_payload(task: str, result: LoopResult, run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "task": task,
        "final_answer": result.final_answer,
        "stop_reason": result.stop_reason,
        "ui_snapshot": _persist_ui_snapshot(run_id, result.trajectory),
        "trajectory": [entry.to_dict() for entry in result.trajectory.entries],
    }
