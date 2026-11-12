"""MCP stdio server entry point.

All 9 tools registered. Tools are fully implemented (no stubs beyond Phase 1.0).
Source clients are instantiated lazily; SourceUnavailableError for missing keys is
caught at the tool level and surfaced as a JSON error, not a crash.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .contracts import BriefReview, ResearchResult
from .database import get_run, get_logical_sources_for_run, init_db
from .engine import run_research_topic, run_verify_claims
from .meter import MeteredClient
from .sources.base import SourceUnavailableError

_REPO_ROOT = Path(__file__).parent.parent.parent
_DB_PATH = str(Path(os.environ.get("RESEARCH_MCP_DB_PATH", str(_REPO_ROOT / "data" / "research.db"))))

mcp = FastMCP("research-mcp")


def _get_clients():
    from .sources.semantic_scholar import SemanticScholarClient
    from .sources.arxiv import ArXivClient
    from .sources.wikipedia import WikipediaClient

    clients = [SemanticScholarClient(), ArXivClient(), WikipediaClient()]

    try:
        from .sources.brave import BraveClient
        clients.append(BraveClient())
    except SourceUnavailableError:
        pass

    try:
        from .sources.google_books import GoogleBooksClient
        clients.append(GoogleBooksClient())
    except SourceUnavailableError:
        pass

    return clients


def _get_meter() -> MeteredClient:
    return MeteredClient(db_path=_DB_PATH)


# ---------------------------------------------------------------------------
# Engine tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def research_topic(
    topic: str,
    profile: Optional[str] = None,
    trusted_sources_only: Optional[bool] = None,
) -> str:
    """Research a topic in depth. Returns a run_id; poll get_run_status / get_run_result."""
    result: ResearchResult = await run_research_topic(
        topic=topic,
        profile=profile,
        trusted_only=trusted_sources_only,
        clients=_get_clients(),
        meter=_get_meter(),
        db_path=_DB_PATH,
    )
    return result.model_dump_json()


@mcp.tool()
async def get_run_status(run_id: str) -> str:
    """Return the current status of a run."""
    row = await get_run(_DB_PATH, run_id)
    if not row:
        return json.dumps({"error": "run_not_found", "run_id": run_id})
    return json.dumps({"run_id": run_id, "status": row["status"], "cost_usd": row["cost_usd"]})


@mcp.tool()
async def get_run_result(run_id: str) -> str:
    """Return the full result of a completed research run."""
    row = await get_run(_DB_PATH, run_id)
    if not row:
        return json.dumps({"error": "run_not_found"})
    if row["status"] != "complete":
        return json.dumps({"error": "run_not_complete", "status": row["status"]})

    sources_raw = await get_logical_sources_for_run(_DB_PATH, run_id)
    run_dir = _REPO_ROOT / "runs" / run_id
    essay_path = str(run_dir / "essay.md")
    essay_content = ""
    if Path(essay_path).exists():
        essay_content = Path(essay_path).read_text()

    return json.dumps({
        "run_id": run_id,
        "status": "complete",
        "cost_usd": row["cost_usd"],
        "essay": essay_content,
        "sources_count": len(sources_raw),
    })


@mcp.tool()
async def verify_claims(
    brief: str,
    trusted_sources_only: Optional[bool] = None,
) -> str:
    """Verify claims in a brief. Returns BriefReview: only surfaced (false/rich) items + passed_count."""
    result: BriefReview = await run_verify_claims(
        brief=brief,
        trusted_only=trusted_sources_only,
        clients=_get_clients(),
        meter=_get_meter(),
        db_path=_DB_PATH,
    )
    return result.model_dump_json()


# ---------------------------------------------------------------------------
# Source tools (direct access)
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_semantic_scholar(query: str, profile: Optional[str] = None) -> str:
    """Search Semantic Scholar for academic papers."""
    from .sources.semantic_scholar import SemanticScholarClient
    client = SemanticScholarClient()
    records = await client.search(query, category=profile)
    return json.dumps([r.model_dump(mode="json") for r in records])


@mcp.tool()
async def search_arxiv(query: str, category: Optional[str] = None) -> str:
    """Search arXiv preprints."""
    from .sources.arxiv import ArXivClient
    client = ArXivClient()
    records = await client.search(query, category=category)
    return json.dumps([r.model_dump(mode="json") for r in records])


@mcp.tool()
async def search_brave(query: str, trusted_sources_only: Optional[bool] = None) -> str:
    """Search the open web via Brave Search (requires BRAVE_API_KEY)."""
    try:
        from .sources.brave import BraveClient
        client = BraveClient()
        records = await client.search(query, trusted_sources_only=trusted_sources_only)
        return json.dumps([r.model_dump(mode="json") for r in records])
    except SourceUnavailableError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def search_wikipedia(query: str) -> str:
    """Search Wikipedia."""
    from .sources.wikipedia import WikipediaClient
    client = WikipediaClient()
    records = await client.search(query)
    return json.dumps([r.model_dump(mode="json") for r in records])


@mcp.tool()
async def search_google_books(query: str) -> str:
    """Search Google Books (requires GOOGLE_BOOKS_API_KEY)."""
    try:
        from .sources.google_books import GoogleBooksClient
        client = GoogleBooksClient()
        records = await client.search(query)
        return json.dumps([r.model_dump(mode="json") for r in records])
    except SourceUnavailableError as e:
        return json.dumps({"error": str(e)})


def main() -> None:
    asyncio.run(_startup())
    mcp.run(transport="stdio")


async def _startup() -> None:
    await init_db(_DB_PATH)


if __name__ == "__main__":
    main()
