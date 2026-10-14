"""
mcp_bridge.py — Integration seam between podcast-brief and Research_MCP.

Converts extracted Claim objects into Research_MCP's pre-split verify pipeline,
preserving speaker/timestamp/quote provenance. Runs research_mcp's async code
inside a ThreadPoolExecutor so we never call asyncio.run() from the event-loop
thread (which is what FastMCP's sync-tool dispatch runs on).
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from pydantic import TypeAdapter

from core.models import Claim, LogicalSource, SurfacedItemWithClaim
from core.config import RESEARCH_DIR


def _get_clients():
    from research_mcp.sources.semantic_scholar import SemanticScholarClient
    from research_mcp.sources.arxiv import ArXivClient
    from research_mcp.sources.wikipedia import WikipediaClient
    from research_mcp.sources.base import SourceUnavailableError

    clients = [SemanticScholarClient(), ArXivClient(), WikipediaClient()]
    try:
        from research_mcp.sources.brave import BraveClient
        clients.append(BraveClient())
    except (SourceUnavailableError, Exception):
        pass
    try:
        from research_mcp.sources.google_books import GoogleBooksClient
        clients.append(GoogleBooksClient())
    except (SourceUnavailableError, Exception):
        pass
    return clients


def _get_db_path() -> str:
    env = os.environ.get("RESEARCH_MCP_DB_PATH")
    if env:
        return env
    from core.config import DATA_DIR
    return str(DATA_DIR / "research.db")


async def _run_research(claims: list[Claim]) -> tuple[list[SurfacedItemWithClaim], str]:
    from research_mcp.database import init_db
    from research_mcp.meter import MeteredClient
    from research_mcp.engine import run_verify_presplit

    db_path = _get_db_path()
    await init_db(db_path)

    clients = _get_clients()
    meter = MeteredClient(db_path=db_path)
    claim_strings = [c.summary for c in claims]

    review = await run_verify_presplit(
        claims=claim_strings,
        trusted_only=None,
        clients=clients,
        meter=meter,
        db_path=db_path,
        floor_effort="light",
    )

    results = []
    for claim, item in zip(claims, review.surfaced):
        # Map LogicalSource fields explicitly — Research_MCP's objects are foreign types
        logical_sources = [
            LogicalSource(
                title=src.title,
                authors=list(src.authors) if src.authors else [],
                published=src.published,
                url=src.url,
                raw_excerpt=src.raw_excerpt or "",
            )
            for src in item.logical_sources
        ]
        results.append(SurfacedItemWithClaim(
            claim=claim,
            triage_correctness=item.triage.correctness,
            triage_effort=item.triage.effort,
            triage_confidence=item.triage.confidence,
            triage_rationale=item.triage.rationale,
            essay_path=item.essay_path,
            logical_sources=logical_sources,
        ))

    return results, review.run_id


def research_claims_via_mcp(claims: list[Claim]) -> tuple[list[SurfacedItemWithClaim], str]:
    """
    Synchronous entry point. Offloads to a worker thread so asyncio.run() always
    gets a fresh event loop — safe whether called from the CLI or an MCP tool
    (where FastMCP's sync-tool dispatch already occupies the event loop).
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, _run_research(claims))
        return future.result()


# ─── Disk persistence ─────────────────────────────────────────────────────────

_ADAPTER = TypeAdapter(list[SurfacedItemWithClaim])


def save_research(episode_id: str, items: list[SurfacedItemWithClaim]) -> Path:
    path = RESEARCH_DIR / f"{episode_id}.json"
    path.write_bytes(_ADAPTER.dump_json(items, indent=2))
    return path


def load_research(episode_id: str) -> list[SurfacedItemWithClaim]:
    path = RESEARCH_DIR / f"{episode_id}.json"
    return _ADAPTER.validate_json(path.read_bytes())
