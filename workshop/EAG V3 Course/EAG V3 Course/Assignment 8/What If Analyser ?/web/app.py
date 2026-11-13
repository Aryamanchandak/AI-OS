"""FastAPI shell for the causal scenario engine.

A full analysis takes long enough (a dozen-plus LLM calls plus web
retrieval) that holding one HTTP request open for it is impractical, so
POST /analyze starts engine.pipeline.run_pipeline() on a background thread
and returns immediately with a job_id. The browser then follows progress
over Server-Sent Events (GET /events/{job_id}) and fetches the rendered
result once it's done (GET /result/{job_id}).

Job state lives in one in-memory dict guarded by a lock — no database or
queue, which is enough for a single-process app with no auth (see
README.md). A failed new run never overwrites `_last_completed`, so the
last successful analysis stays visible while a fresh one runs or fails.

Run with (from the project root):
    .venv/bin/python -m uvicorn web.app:app --reload
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from engine.pipeline import run_pipeline
from engine.presentation import cell, edge_robustness, graph_to_dot, impact_class

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
MAX_JOBS = 20


@dataclass
class JobState:
    """Mutable in-memory state for one background analysis."""

    id: str
    brief: str
    mode: str
    created_at: float = field(default_factory=time)
    status: str = "running"
    events: list[dict] = field(default_factory=list)
    result: dict | None = None
    error: str = ""
    usage: dict = field(default_factory=dict)


app = FastAPI(title="What If", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals.update(cell=cell, impact_class=impact_class)

_jobs: dict[str, JobState] = {}
_jobs_lock = threading.Lock()
_workers = ThreadPoolExecutor(max_workers=4, thread_name_prefix="whatif-analysis")
_last_completed: dict | None = None


def _append_event(job_id: str, step_id: str, message: str, kind: str = "progress") -> None:
    """Append one progress event without exposing mutable job internals."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.events.append(
                {
                    "type": kind,
                    "step_id": step_id,
                    "message": message,
                }
            )


def _run_job(job_id: str) -> None:
    """Execute one job and commit its result only after full success."""
    global _last_completed

    with _jobs_lock:
        job = _jobs[job_id]
        brief, mode = job.brief, job.mode

    def progress(step_id: str, message: str) -> None:
        _append_event(job_id, step_id, message)

    def usage_update(usage: dict) -> None:
        """Publish the latest immutable usage snapshot to the browser."""
        with _jobs_lock:
            current = _jobs.get(job_id)
            if current is None:
                return
            current.usage = usage
            current.events.append(
                {
                    "type": "usage",
                    "step_id": "model_usage",
                    "message": "Model usage updated",
                    "usage": usage,
                }
            )

    try:
        result = run_pipeline(
            brief,
            mode,
            on_progress=progress,
            on_usage=usage_update,
        )
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        with _jobs_lock:
            job = _jobs[job_id]
            job.status = "failed"
            job.error = message
            job.events.append(
                {
                    "type": "error",
                    "step_id": "analysis_failed",
                    "message": (
                        "The new analysis failed. The previous completed result "
                        f"was kept. {message}"
                    ),
                }
            )
        return

    # The shared completed result is assigned atomically only here. Failed jobs
    # therefore cannot overwrite a usable analysis.
    with _jobs_lock:
        job = _jobs[job_id]
        job.result = result
        job.status = "completed"
        _last_completed = result
        job.events.append(
            {
                "type": "complete",
                "step_id": "analysis_complete",
                "message": "Scenario map ready",
            }
        )


def _trim_finished_jobs() -> None:
    """Bound process memory while never removing active work."""
    if len(_jobs) < MAX_JOBS:
        return
    finished = sorted(
        (job for job in _jobs.values() if job.status != "running"),
        key=lambda job: job.created_at,
    )
    for job in finished[: max(0, len(_jobs) - MAX_JOBS + 1)]:
        _jobs.pop(job.id, None)


def _safe_source_url(value: str) -> str | None:
    """Allow only public web link schemes in result templates."""
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} else None


def _result_context(analysis: dict) -> dict:
    """Prepare display-only structures while leaving Jinja to own HTML escaping."""
    graph = analysis["graph"]
    outcome_nodes = [node for node in graph.nodes if node.node_type == "outcome"]
    matrix_rows = []
    scenario_cards = []

    for index, (name, narrative, resolved_graph) in enumerate(
        zip(
            analysis["names"],
            analysis["narratives"],
            analysis["resolved"],
        ),
        start=1,
    ):
        by_id = {node.id: node for node in resolved_graph.nodes}
        outcomes = [
            {"definition": outcome, "resolved": by_id[outcome.id]}
            for outcome in outcome_nodes
        ]
        matrix_rows.append({"name": name, "outcomes": outcomes})
        scenario_cards.append(
            {
                "index": index,
                "name": name,
                "narrative": narrative,
                "outcomes": outcomes,
            }
        )

    source_by_id = {source.id: source for source in analysis["sources"]}
    claims = [
        {
            "claim": claim,
            "source_name": (
                source_by_id[claim.source_id].title
                if claim.source_id in source_by_id
                else claim.source_id
            ),
        }
        for claim in analysis["claims"]
    ]
    robustness = edge_robustness(graph, analysis["assignments"][0])
    robustness_rows = robustness.to_dict(orient="records")

    return {
        "analysis": analysis,
        "graph": graph,
        "outcome_nodes": outcome_nodes,
        "matrix_rows": matrix_rows,
        "scenario_cards": scenario_cards,
        "claims_with_sources": claims,
        "robustness_rows": robustness_rows,
        "supported_edges": sum(
            edge.evidence_status == "supported" for edge in graph.edges
        ),
        "graph_dot": graph_to_dot(graph),
        "safe_source_url": _safe_source_url,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the analysis form and the latest completed result, if any."""
    with _jobs_lock:
        last_completed = _last_completed
    context = {
        "request": request,
        "has_api_key": bool(
            os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        ),
        "last_completed": last_completed,
    }
    if last_completed is not None:
        context.update(_result_context(last_completed))
    return templates.TemplateResponse(request, "index.html", context)


@app.post("/analyze")
async def analyze(request: Request) -> JSONResponse:
    """Start a background analysis and return its progress-stream identifier."""
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Expected a JSON request.") from exc

    brief = str(payload.get("brief", "")).strip()
    mode = str(payload.get("mode", "quick")).strip().casefold()
    if not brief:
        raise HTTPException(status_code=422, detail="Type a situation first.")
    if len(brief) > 4_000:
        raise HTTPException(
            status_code=422,
            detail="Keep the situation under 4,000 characters.",
        )
    if mode not in {"quick", "deep"}:
        raise HTTPException(status_code=422, detail="Choose Quick or Deep.")

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _trim_finished_jobs()
        _jobs[job_id] = JobState(id=job_id, brief=brief, mode=mode)
    _workers.submit(_run_job, job_id)
    return JSONResponse({"job_id": job_id}, status_code=202)


@app.get("/events/{job_id}")
async def events(job_id: str) -> StreamingResponse:
    """Stream ordered pipeline progress as Server-Sent Events."""
    with _jobs_lock:
        if job_id not in _jobs:
            raise HTTPException(status_code=404, detail="Analysis job not found.")

    async def event_stream():
        cursor = 0
        while True:
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job is None:
                    return
                pending = list(job.events[cursor:])
                terminal = job.status in {"completed", "failed"}
            for event in pending:
                cursor += 1
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if terminal and not pending:
                return
            await asyncio.sleep(0.2)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/result/{job_id}", response_class=HTMLResponse)
async def result(request: Request, job_id: str) -> HTMLResponse:
    """Return the finished, autoescaped result fragment for one job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Analysis job not found.")
        status, analysis, error = job.status, job.result, job.error
    if status == "running":
        raise HTTPException(status_code=409, detail="Analysis is still running.")
    if status == "failed" or analysis is None:
        raise HTTPException(status_code=500, detail=error or "Analysis failed.")

    context = {"request": request, **_result_context(analysis)}
    return templates.TemplateResponse(request, "partials/result.html", context)


@app.on_event("shutdown")
def shutdown_workers() -> None:
    """Release worker threads during a clean server shutdown."""
    _workers.shutdown(wait=False, cancel_futures=True)
