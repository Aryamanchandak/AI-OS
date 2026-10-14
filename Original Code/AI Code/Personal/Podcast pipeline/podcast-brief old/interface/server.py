"""
server.py — HTTP endpoint for iOS Shortcut integration + MCP server (mounted at /mcp).

Run with:
    uvicorn interface.server:app --host 0.0.0.0 --port 8765

iOS Shortcut integration: POST to /brief with {"url": "<shared url>"}
MCP clients: connect to http://<host>:8765/mcp (Streamable HTTP transport)

For phone-to-laptop access, expose via Tailscale (recommended) or ngrok.
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

load_dotenv()

from core import pipeline
from core.config import find_show_by_url
from interface.mcp_server import mcp


API_TOKEN = os.getenv("PODCAST_BRIEF_API_TOKEN", "")


def _check_token(provided: Optional[str]):
    if not API_TOKEN:
        return
    if provided != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wire the MCP session manager into the FastAPI lifespan so /mcp works."""
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Podcast Brief",
    description="Generate research briefs from podcast URLs.",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount the MCP Streamable HTTP transport
app.mount("/mcp", mcp.streamable_http_app())


class BriefRequest(BaseModel):
    url: str
    profile: Optional[str] = None
    transcript_only: bool = False
    skip_research: bool = False


@app.get("/")
def root():
    return {"service": "podcast-brief", "status": "ok"}


@app.post("/brief")
def create_brief(
    req: BriefRequest,
    background_tasks: BackgroundTasks,
    token: Optional[str] = None,
):
    """
    Queue a URL for brief generation.
    Returns immediately — actual processing happens in a background thread.
    """
    _check_token(token)

    show = find_show_by_url(req.url)
    profile = req.profile or (show.profile if show else "hybrid")

    def _run():
        try:
            pipeline.run_pipeline(
                url=req.url,
                show=show,
                profile=profile,
                speakers_hint=show.speakers_hint if show else "",
                show_name=show.name if show else "Manual entry",
                transcript_only=req.transcript_only,
                skip_research=req.skip_research,
            )
        except Exception as e:
            print(f"Pipeline failed for {req.url}: {e}", flush=True)

    background_tasks.add_task(_run)

    return {
        "status": "queued",
        "url": req.url,
        "profile": profile,
        "show": show.name if show else None,
        "transcript_only": req.transcript_only,
        "message": "Brief is being generated. It will appear in your Reader inbox shortly.",
    }


@app.get("/recent")
def recent(limit: int = 10, token: Optional[str] = None):
    """List recently processed episodes."""
    _check_token(token)
    from core import state
    state.init_db()
    return {"episodes": state.get_recent_episodes(limit=limit)}
