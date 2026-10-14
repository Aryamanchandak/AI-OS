"""Gemini-grounded books search source client (uses GEMINI_API_KEY, no extra key needed)."""
from __future__ import annotations

import os

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ..contracts import SourceRecord
from .base import SourceClient, SourceUnavailableError
from .gemini_web import _BASE_URL, _client, _retry_on_transient, _parse_grounding

_BOOKS_PREFIX = "Find books about: "


class GoogleBooksClient(SourceClient):
    name = "google_books"
    source_tier = "book"

    @retry(
        retry=retry_if_exception(_retry_on_transient),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def search(self, query: str, **kwargs) -> list[SourceRecord]:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise SourceUnavailableError("GEMINI_API_KEY not set")
        limit = kwargs.get("limit", 10)
        books_query = f"{_BOOKS_PREFIX}{query}"
        body = {
            "contents": [{"role": "user", "parts": [{"text": books_query}]}],
            "tools": [{"google_search": {}}],
        }
        resp = await _client.post(f"{_BASE_URL}?key={key}", json=body)
        resp.raise_for_status()
        return _parse_grounding(resp.json(), self.name, self.source_tier, limit)
