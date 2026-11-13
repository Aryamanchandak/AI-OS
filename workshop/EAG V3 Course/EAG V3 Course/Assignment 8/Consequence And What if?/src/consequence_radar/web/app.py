from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import Settings, get_settings
from ..models import NewsBatch
from ..pipeline import Pipeline
from ..report import export_markdown
from ..storage import Repository

BASE = Path(__file__).parent
TERMINAL = {"completed", "completed_with_warnings", "failed", "report_validation_failed"}


def create_app(settings: Settings | None = None, repository: Repository | None = None, pipeline_factory=None) -> FastAPI:
    settings = settings or get_settings()
    repo = repository or Repository(settings.database_url)
    repo.init_schema()
    workers = ThreadPoolExecutor(max_workers=settings.worker_count, thread_name_prefix="radar-run")
    pipeline_factory = pipeline_factory or (lambda: Pipeline(settings, repo))
    @asynccontextmanager
    async def lifespan(_app):
        yield
        workers.shutdown(wait=False, cancel_futures=True)
    app = FastAPI(title="Consequence Radar", version="0.1.0", lifespan=lifespan)
    app.state.repo, app.state.settings, app.state.workers = repo, settings, workers
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    templates = Jinja2Templates(directory=BASE / "templates")

    def index_response(request: Request, *, form_error: str = "", form_value: str = "", status_code: int = 200):
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "runs": repo.list_runs(),
                "has_key": bool(settings.api_key),
                "form_error": form_error,
                "form_value": form_value,
            },
            status_code=status_code,
        )

    def start(run_id: str):
        try: pipeline_factory().run(run_id)
        except Exception as exc:
            repo.set_status(run_id, "failed", error=str(exc)); repo.add_event(run_id, "failed", str(exc), "error")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return index_response(request)

    @app.post("/runs", response_class=HTMLResponse)
    async def create_run_from_form(request: Request, news: str = Form(...)):
        """Progressive-enhancement fallback when the browser script cannot run."""
        lines = [line.strip() for line in news.splitlines() if line.strip()]
        try:
            batch = NewsBatch(items=[{"url": url} for url in lines])
        except ValueError:
            return index_response(
                request,
                form_error="Enter 1–100 complete http:// or https:// article URLs, one per line.",
                form_value=news,
                status_code=422,
            )
        run_id = repo.create_run(batch)
        workers.submit(start, run_id)
        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_page(request: Request, run_id: str):
        run = repo.get_run(run_id)
        if not run: raise HTTPException(404, "Run not found")
        context = {"request": request, "run": run, "report": repo.artifact(run_id, "report") or repo.artifact(run_id, "report_draft"), "validation": repo.artifact(run_id, "report_validation"), "candidates": repo.artifact(run_id, "candidates") or [], "graph": repo.artifact(run_id, "graph"), "cases": repo.artifact(run_id, "cases"), "audit": repo.artifacts(run_id), "events": repo.events_since(run_id), "usage": repo.artifact(run_id, "usage")}
        return templates.TemplateResponse(request, "run.html", context)

    @app.post("/api/v1/runs", status_code=202)
    async def create_run(batch: NewsBatch):
        run_id = repo.create_run(batch)
        workers.submit(start, run_id)
        return {"run_id": run_id, "status": "queued", "url": f"/runs/{run_id}"}

    @app.get("/api/v1/runs/{run_id}")
    async def run_status(run_id: str):
        run = repo.get_run(run_id)
        if not run: raise HTTPException(404, "Run not found")
        return run

    @app.get("/api/v1/runs/{run_id}/events")
    async def events(request: Request, run_id: str, after: int = 0):
        if not repo.get_run(run_id): raise HTTPException(404, "Run not found")
        # A reconnecting EventSource resends the last id it saw. Ignoring it
        # replayed the whole run and appended every line to the list a second
        # time on each reconnect.
        resume = request.headers.get("last-event-id", "")
        if resume.isdigit(): after = max(after, int(resume))

        async def stream():
            cursor = after
            # A run whose worker was cancelled at shutdown stays non-terminal
            # for good; without a ceiling this generator polls SQLite forever.
            deadline = time.monotonic() + settings.max_wall_time_seconds + 60
            while True:
                for event in repo.events_since(run_id, cursor):
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                state = repo.get_run(run_id)
                if state and state["status"] in TERMINAL:
                    # The pipeline sets the terminal status *before* writing its
                    # closing event. Returning the moment the status flips can
                    # land in that window and drop the completion line, leaving
                    # the browser on the progress view until it reconnects. One
                    # last pause and drain closes the gap.
                    await asyncio.sleep(0.35)
                    for event in repo.events_since(run_id, cursor):
                        cursor = event["sequence"]
                        yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                    return
                # Client disconnects are Starlette's job: it cancels this
                # generator itself, and calling request.is_disconnected() here
                # would contend with its listener for the same receive channel.
                if time.monotonic() > deadline: return
                await asyncio.sleep(0.35)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/v1/runs/{run_id}/report")
    async def report(run_id: str, format: str = "json"):
        data = repo.artifact(run_id, "report")
        if not data: raise HTTPException(404, "Validated report not available")
        if format == "markdown":
            from ..models import NewsletterReport
            return PlainTextResponse(export_markdown(NewsletterReport.model_validate(data)), media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="consequence-radar-{run_id}.md"'})
        return data

    @app.get("/api/v1/runs/{run_id}/graph")
    async def graph(run_id: str):
        data = repo.artifact(run_id, "graph")
        if not data: raise HTTPException(404, "Graph not available")
        return data

    @app.get("/api/v1/runs/{run_id}/audit")
    async def audit(run_id: str):
        if not repo.get_run(run_id): raise HTTPException(404, "Run not found")
        return {"run": repo.get_run(run_id), "artifacts": repo.artifacts(run_id), "events": repo.events_since(run_id)}

    @app.get("/api/v1/runs/{run_id}/export")
    async def export(run_id: str):
        run = repo.get_run(run_id, include_artifacts=True)
        if not run: raise HTTPException(404, "Run not found")
        run["events"] = repo.events_since(run_id)
        return JSONResponse(run, headers={"Content-Disposition": f'attachment; filename="consequence-radar-{run_id}.json"'})

    @app.get("/health")
    async def health():
        return {"status": "ok", "database": "ok", "live_credentials_configured": bool(settings.api_key)}

    return app


app = create_app()


def run():
    import uvicorn
    settings = get_settings()
    uvicorn.run("consequence_radar.web.app:app", host=settings.web_host, port=settings.web_port, reload=False)
