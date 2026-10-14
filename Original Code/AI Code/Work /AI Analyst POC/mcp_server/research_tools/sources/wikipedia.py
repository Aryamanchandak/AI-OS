"""Wikipedia source client (no API key required; MediaWiki REST API)."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ..contracts import SourceRecord
from .base import SourceClient

_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
_client = httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "ResearchMCP/1.0 (academic research tool)"})


def _retry_on_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ReadTimeout):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 503)


class WikipediaClient(SourceClient):
    name = "wikipedia"
    source_tier = "encyclopedic"

    @retry(
        retry=retry_if_exception(_retry_on_rate_limit),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def search(self, query: str, **kwargs) -> list[SourceRecord]:
        limit = kwargs.get("limit", 5)
        resp = await _client.get(
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
            snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
            records.append(
                SourceRecord(
                    source=self.name,
                    external_id=title.replace(" ", "_"),
                    title=title,
                    authors=[],
                    published=None,
                    url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    raw_excerpt=snippet,
                    source_tier=self.source_tier,
                    fetched_at=datetime.now(timezone.utc),
                )
            )
        return records
