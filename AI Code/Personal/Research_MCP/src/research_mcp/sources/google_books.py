"""Google Books source client (requires GOOGLE_BOOKS_API_KEY env var)."""
from __future__ import annotations

import os
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ..contracts import Provenance, SourceRecord
from .base import SourceClient, SourceUnavailableError

_API_URL = "https://www.googleapis.com/books/v1/volumes"


def _retry_on_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ReadTimeout):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 503)


class GoogleBooksClient(SourceClient):
    name = "google_books"

    def __init__(self):
        key = os.environ.get("GOOGLE_BOOKS_API_KEY")
        if not key:
            raise SourceUnavailableError("GOOGLE_BOOKS_API_KEY not set")
        self._key = key
        self._http = httpx.AsyncClient(timeout=30.0)

    @retry(
        retry=retry_if_exception(_retry_on_rate_limit),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def search(self, query: str, **kwargs) -> list[SourceRecord]:
        limit = kwargs.get("limit", 10)
        resp = await self._http.get(
            _API_URL,
            params={"q": query, "maxResults": limit, "key": self._key},
        )
        resp.raise_for_status()
        data = resp.json()

        records: list[SourceRecord] = []
        for item in data.get("items", []):
            vi = item.get("volumeInfo", {})
            volume_id = item.get("id", "")
            authors = vi.get("authors") or []
            published = vi.get("publishedDate")
            description = vi.get("description") or ""
            canonical_url = vi.get("canonicalVolumeLink") or f"https://books.google.com/books?id={volume_id}"
            records.append(
                SourceRecord(
                    source=self.name,
                    external_id=volume_id,
                    title=vi.get("title") or "",
                    authors=authors,
                    published=published,
                    url=canonical_url,
                    raw_excerpt=description[:2000],
                    fetched_at=datetime.utcnow(),
                    provenance=Provenance(
                        query=query,
                        source_tier="book",
                        fetched_via=self.name,
                    ),
                )
            )
        return records

    async def aclose(self) -> None:
        await self._http.aclose()
