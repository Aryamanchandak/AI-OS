"""Wikipedia source client (no API key required; MediaWiki REST API)."""
from __future__ import annotations

import re
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ..contracts import Provenance, SourceRecord
from .base import SourceClient

_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


def _retry_on_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ReadTimeout):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 503)


class WikipediaClient(SourceClient):
    name = "wikipedia"

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "ResearchMCP/1.0 (academic research tool)"})

    @retry(
        retry=retry_if_exception(_retry_on_rate_limit),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def search(self, query: str, **kwargs) -> list[SourceRecord]:
        limit = kwargs.get("limit", 5)
        # Step 1: full-text search to get titles
        resp = await self._http.get(
            _SEARCH_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "format": "json",
            },
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])

        records: list[SourceRecord] = []
        for item in results:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            snippet = re.sub(r"<[^>]+>", "", snippet)

            records.append(
                SourceRecord(
                    source=self.name,
                    external_id=title.replace(" ", "_"),
                    title=title,
                    authors=[],
                    published=None,
                    url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    raw_excerpt=snippet,
                    fetched_at=datetime.utcnow(),
                    provenance=Provenance(
                        query=query,
                        source_tier="encyclopedic",
                        fetched_via=self.name,
                    ),
                )
            )
        return records

    async def aclose(self) -> None:
        await self._http.aclose()
