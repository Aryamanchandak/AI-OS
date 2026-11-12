"""
Research search tools with uniform error handling.
functools.wraps preserves each function's signature so FastMCP generates correct schemas.
"""
from __future__ import annotations
import functools
import json
import logging
from typing import Optional

from tool_registry import register
from .clients import arxiv, semantic_scholar, wikipedia, gemini_web, google_books

from research_tools.sources.base import SourceUnavailableError
from research_tools.contracts import SourceRecord

logger = logging.getLogger(__name__)


def _to_json(records: list[SourceRecord]) -> str:
    return json.dumps([r.model_dump(mode="json") for r in records])


def _err(kind: str, detail: str) -> str:
    return json.dumps({"error": kind, "detail": detail})


def _wrap_search(source_name: str):
    """Adds uniform error handling. functools.wraps preserves the original signature."""
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except SourceUnavailableError as e:
                return _err("source_unavailable", str(e))
            except TimeoutError:
                return _err("timeout", f"{source_name} did not respond in time")
            except Exception as e:
                logger.exception("Unexpected error in %s", fn.__name__)
                return _err("unexpected", str(e))
        return wrapper
    return decorator


@register(group="research")
@_wrap_search("arXiv")
async def search_arxiv(query: str, category: Optional[str] = None) -> str:
    """Search arXiv preprints. Optional category filter e.g. 'cs.AI'."""
    records = await arxiv.search(query, category=category)
    return _to_json(records)


@register(group="research")
@_wrap_search("Semantic Scholar")
async def search_semantic_scholar(query: str) -> str:
    """Search Semantic Scholar for peer-reviewed academic papers."""
    records = await semantic_scholar.search(query)
    return _to_json(records)


@register(group="research")
@_wrap_search("Wikipedia")
async def search_wikipedia(query: str) -> str:
    """Search Wikipedia articles."""
    records = await wikipedia.search(query)
    return _to_json(records)


@register(group="research")
@_wrap_search("Gemini Web Search")
async def search_web(query: str) -> str:
    """Search the open web via Gemini Google Search grounding."""
    records = await gemini_web.search(query)
    return _to_json(records)


@register(group="research")
@_wrap_search("Google Books")
async def search_google_books(query: str) -> str:
    """Search for books via Gemini Google Search grounding."""
    records = await google_books.search(query)
    return _to_json(records)
