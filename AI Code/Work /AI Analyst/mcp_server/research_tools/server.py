"""MCP stdio server entry point.

One MCP tool per source. Each tool takes a query, calls the source's API, and
returns results as JSON. No engine, database, or synthesis layer.
"""
from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .contracts import SourceRecord
from .sources.base import SourceUnavailableError
from .sources.arxiv import ArXivClient
from .sources.gemini_web import GeminiWebClient
from .sources.google_books import GoogleBooksClient
from .sources.semantic_scholar import SemanticScholarClient
from .sources.wikipedia import WikipediaClient

mcp = FastMCP("research-mcp")

_arxiv = ArXivClient()
_semantic_scholar = SemanticScholarClient()
_wikipedia = WikipediaClient()
_gemini_web = GeminiWebClient()
_google_books = GoogleBooksClient()


def _to_json(records: list[SourceRecord]) -> str:
    return json.dumps([r.model_dump(mode="json") for r in records])


@mcp.tool()
async def search_semantic_scholar(query: str) -> str:
    """Search Semantic Scholar for academic papers."""
    try:
        records = await _semantic_scholar.search(query)
        return _to_json(records)
    except SourceUnavailableError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def search_arxiv(query: str, category: Optional[str] = None) -> str:
    """Search arXiv preprints."""
    try:
        records = await _arxiv.search(query, category=category)
        return _to_json(records)
    except SourceUnavailableError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def search_wikipedia(query: str) -> str:
    """Search Wikipedia."""
    try:
        records = await _wikipedia.search(query)
        return _to_json(records)
    except SourceUnavailableError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def search_web(query: str) -> str:
    """Search the open web via Gemini Google Search grounding."""
    try:
        records = await _gemini_web.search(query)
        return _to_json(records)
    except SourceUnavailableError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def search_google_books(query: str) -> str:
    """Search for books via Gemini Google Search grounding."""
    try:
        records = await _google_books.search(query)
        return _to_json(records)
    except SourceUnavailableError as e:
        return json.dumps({"error": str(e)})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
