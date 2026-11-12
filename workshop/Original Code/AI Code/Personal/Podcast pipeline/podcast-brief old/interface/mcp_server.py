"""
mcp_server.py — FastMCP server exposing the podcast-brief pipeline as MCP tools.

Primary transport: Streamable HTTP, mounted at /mcp on the FastAPI server.
Fallback: stdio via the `podcast-brief-mcp` entry point (main() below).

Every tool is a plain sync def — FastMCP's async tool.run() calls sync functions
directly, so all Anthropic calls are routed via core.llm (tenacity-backed) and the
research stage uses ThreadPoolExecutor to isolate asyncio.run() from the event loop.
"""

from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP

from core.models import (
    DeliverResult,
    ExtractResult,
    IngestResult,
    ResearchResult,
    SynthesizeResult,
    TranscribeResult,
)

mcp = FastMCP(
    "podcast-brief",
    # When mounted at /mcp in FastAPI, the mount strips the prefix so the sub-app
    # sees "/" — configure the internal streamable HTTP route at "/" to match.
    streamable_http_path="/",
    instructions=(
        "You have access to a podcast research brief pipeline. "
        "Use generate_brief(url) to run the full pipeline in one shot. "
        "For step-by-step control, call the per-stage tools in order: "
        "ingest_audio → transcribe_episode → extract_claims → research_claims → "
        "synthesize_brief → deliver_brief. "
        "After each per-stage tool, call get_episode_status(episode_id) and confirm "
        "the expected 'runs' row is 'completed' before proceeding to the next stage."
    ),
)


# ─── Orchestrator tool ────────────────────────────────────────────────────────

@mcp.tool()
def generate_brief(
    url: str,
    profile: str = "hybrid",
    show: str = "",
    transcript_only: bool = False,
    skip_research: bool = False,
) -> dict:
    """
    Run the full pipeline on a podcast URL and deliver a research brief to Readwise Reader.

    Stages run in fixed order in Python — no model decides the sequence.
    profile: 'hybrid' | 'academic' | 'current_events'
    show: optional show name (must match a name in shows.yaml for per-show config)
    transcript_only: skip extraction/research/synthesis; deliver the raw transcript
    skip_research: skip the Research_MCP stage (faster, cheaper, less context)
    """
    from core.config import load_shows
    from core.orchestrator import process_episode

    show_obj = None
    if show:
        for s in load_shows():
            if s.name.lower() == show.lower():
                show_obj = s
                break

    return process_episode(
        url=url,
        show=show_obj,
        profile=profile,
        show_name=show or "Manual entry",
        transcript_only=transcript_only,
        skip_research=skip_research,
    )


# ─── Per-stage tools ──────────────────────────────────────────────────────────

@mcp.tool()
def ingest_audio(
    url: str,
    show_name: str = "Manual entry",
    profile: str = "hybrid",
) -> IngestResult:
    """
    Download audio from a URL and register the episode.
    Returns episode_id needed for subsequent stage tools.
    """
    from core.stages import stage_ingest
    return stage_ingest(url, show_name=show_name, profile=profile)


@mcp.tool()
def transcribe_episode(episode_id: str, speakers_hint: str = "") -> TranscribeResult:
    """
    Transcribe the audio for episode_id using Deepgram Nova-3.
    Run ingest_audio first.
    """
    from core.stages import stage_transcribe
    return stage_transcribe(episode_id, speakers_hint=speakers_hint)


@mcp.tool()
def extract_claims(episode_id: str) -> ExtractResult:
    """
    Extract typed, research-worthy claims from the transcript using Claude Sonnet.
    profile and show_name are loaded from the DB record created during ingest.
    Run transcribe_episode first.
    """
    from core.stages import stage_extract
    return stage_extract(episode_id)


@mcp.tool()
def research_claims(episode_id: str) -> ResearchResult:
    """
    Research extracted claims via Research_MCP (Semantic Scholar, arXiv, Wikipedia, Brave).
    Results are persisted to data/research_items/<episode_id>.json.
    Run extract_claims first.
    """
    from core.stages import stage_research
    return stage_research(episode_id)


@mcp.tool()
def synthesize_brief(episode_id: str) -> SynthesizeResult:
    """
    Synthesize the final research brief using Claude Opus.
    Loads transcript, extraction, and research items from disk.
    Run extract_claims (and optionally research_claims) first.
    """
    from core.stages import stage_synthesize
    return stage_synthesize(episode_id)


@mcp.tool()
def deliver_brief(episode_id: str, transcript_only: bool = False) -> DeliverResult:
    """
    Format and push the brief (or raw transcript) to Readwise Reader.
    Run synthesize_brief first (or transcribe_episode for transcript_only=True).
    """
    from core.stages import stage_deliver
    return stage_deliver(episode_id, transcript_only=transcript_only)


# ─── Query / admin tools ──────────────────────────────────────────────────────

@mcp.tool()
def list_recent_episodes(limit: int = 20) -> list[dict]:
    """List recently processed episodes from the local SQLite state DB."""
    from core import state
    state.init_db()
    return state.get_recent_episodes(limit=limit)


@mcp.tool()
def get_episode_status(episode_id: str) -> dict:
    """
    Return the current episode record and its stage run log.
    Use this as a verification gate between per-stage tool calls.
    """
    from core import state
    state.init_db()
    episode = state.get_episode(episode_id)
    runs = state.get_runs(episode_id)
    return {"episode": episode, "runs": runs}


@mcp.tool()
def list_shows() -> list[dict]:
    """List all configured shows from shows.yaml."""
    from core.config import load_shows
    shows = load_shows()
    return [s.model_dump() for s in shows]


@mcp.tool()
def poll_shows(limit_per_show: int = 3, dry_run: bool = False) -> dict:
    """
    Poll all active shows for new episodes and process them.
    dry_run=True reports what would be processed without running the pipeline.
    """
    from ingestion.poll import poll_all_shows
    poll_all_shows(limit_per_show=limit_per_show, dry_run=dry_run)
    return {"status": "poll complete"}


@mcp.tool()
def check_config() -> dict:
    """Check API keys, token validity, and show configuration."""
    from core.config import check_config as _check_config
    return _check_config()


# ─── Resource: read a full brief ──────────────────────────────────────────────

@mcp.resource("brief://{episode_id}")
def read_brief(episode_id: str) -> str:
    """Read the full markdown brief for an episode without bloating tool responses."""
    from core.config import BRIEF_DIR
    path = BRIEF_DIR / f"{episode_id}.md"
    if not path.exists():
        return f"No brief found for episode {episode_id}."
    return path.read_text()


# ─── Stdio entry point ────────────────────────────────────────────────────────

def main():
    """Run the MCP server over stdio (fallback transport)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
