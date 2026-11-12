"""Gemini-grounded web search source client (uses GEMINI_API_KEY, no extra key needed)."""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ..contracts import SourceRecord
from .base import SourceClient, SourceUnavailableError

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_client = httpx.AsyncClient(timeout=30.0)


def _retry_on_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ReadTimeout):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 503)


def _parse_grounding(d: dict, source_name: str, source_tier: str, limit: int) -> list[SourceRecord]:
    candidates = d.get("candidates") or []
    if not candidates:
        return []
    grounding = candidates[0].get("groundingMetadata") or {}
    chunks = (grounding.get("groundingChunks") or [])[:limit]
    supports = grounding.get("groundingSupports") or []

    chunk_excerpts: dict[int, list[str]] = defaultdict(list)
    for sup in supports:
        text = (sup.get("segment") or {}).get("text", "")
        for idx in sup.get("groundingChunkIndices") or []:
            if text:
                chunk_excerpts[idx].append(text)

    records: list[SourceRecord] = []
    for i, chunk in enumerate(chunks):
        web = chunk.get("web") or {}
        url = web.get("uri", "")
        title = web.get("title", "")
        if not url:
            continue
        excerpt = " ".join(chunk_excerpts.get(i, []))[:2000]
        records.append(
            SourceRecord(
                source=source_name,
                external_id=url,
                title=title,
                authors=[],
                published=None,
                url=url,
                raw_excerpt=excerpt,
                source_tier=source_tier,
                fetched_at=datetime.now(timezone.utc),
            )
        )
    return records


class GeminiWebClient(SourceClient):
    name = "gemini_web"
    source_tier = "open_web"

    @retry(
        retry=retry_if_exception(_retry_on_transient),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def search(self, query: str, **kwargs) -> list[SourceRecord]:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise SourceUnavailableError("GEMINI_API_KEY not set")
        limit = kwargs.get("limit", 10)
        body = {
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "tools": [{"google_search": {}}],
        }
        resp = await _client.post(f"{_BASE_URL}?key={key}", json=body)
        resp.raise_for_status()
        return _parse_grounding(resp.json(), self.name, self.source_tier, limit)
