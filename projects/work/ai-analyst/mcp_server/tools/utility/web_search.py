"""
Web search: Gemini Google Search primary, DuckDuckGo fallback. Hard-capped at 5 results.
"""
from __future__ import annotations

import os
from collections import defaultdict

import httpx

from tool_registry import register
import usage as _usage

MAX_SEARCH_RESULTS = 5
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def _gemini_search(query: str, max_results: int) -> list[dict]:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return []
    body = {
        "contents": [{"role": "user", "parts": [{"text": query}]}],
        "tools": [{"google_search": {}}],
    }
    try:
        resp = httpx.post(f"{_GEMINI_URL}?key={key}", json=body, timeout=30.0)
        resp.raise_for_status()
    except Exception:
        return []
    d = resp.json()
    candidates = d.get("candidates") or []
    if not candidates:
        return []
    grounding = candidates[0].get("groundingMetadata") or {}
    chunks = (grounding.get("groundingChunks") or [])[:max_results]
    supports = grounding.get("groundingSupports") or []
    chunk_excerpts: dict[int, list[str]] = defaultdict(list)
    for sup in supports:
        text = (sup.get("segment") or {}).get("text", "")
        for idx in sup.get("groundingChunkIndices") or []:
            if text:
                chunk_excerpts[idx].append(text)
    return [
        {
            "title": (chunk.get("web") or {}).get("title", ""),
            "url": (chunk.get("web") or {}).get("uri", ""),
            "snippet": " ".join(chunk_excerpts.get(i, [])),
        }
        for i, chunk in enumerate(chunks)
        if (chunk.get("web") or {}).get("uri")
    ]


def _ddg_search(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    hits: list[dict] = []
    with DDGS() as ddgs:
        for backend in ("auto", "html", "lite"):
            try:
                hits = list(ddgs.text(query, max_results=max_results, backend=backend))
            except Exception:
                hits = []
            if hits:
                break
    return [
        {
            "title": h.get("title", ""),
            "url": h.get("href", ""),
            "snippet": h.get("body", ""),
        }
        for h in hits
    ]


@register(group="utility")
def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web (Gemini Google Search primary, DuckDuckGo fallback). Hard-capped at 5 results. Example: web_search("python asyncio tutorial", 3)."""
    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))
    results = _gemini_search(query, max_results)
    if results:
        return results
    results = _ddg_search(query, max_results)
    _usage.bump("duckduckgo")
    return results
