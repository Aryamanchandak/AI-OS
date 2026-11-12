"""Semantic Scholar source client.

No API key required (100 req/5min free tier). Set SEMANTIC_SCHOLAR_API_KEY for
10 req/sec (free key at https://www.semanticscholar.org/product/api).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ..contracts import SourceRecord
from .base import SourceClient

_API_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "paperId,externalIds,title,authors,year,abstract,url"
_headers = {"User-Agent": "ResearchMCP/1.0 (academic research tool)"}
_api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
if _api_key:
    _headers["x-api-key"] = _api_key
_client = httpx.AsyncClient(timeout=30.0, headers=_headers)


def _retry_on_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ReadTimeout):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 503)


class SemanticScholarClient(SourceClient):
    name = "semantic_scholar"
    source_tier = "academic"

    @retry(
        retry=retry_if_exception(_retry_on_rate_limit),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def search(self, query: str, **kwargs) -> list[SourceRecord]:
        limit = kwargs.get("limit", 10)
        resp = await _client.get(
            f"{_API_BASE}/paper/search",
            params={"query": query, "fields": _FIELDS, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        records: list[SourceRecord] = []
        for paper in data.get("data", []):
            ext_ids = paper.get("externalIds") or {}
            external_id = ext_ids.get("DOI") or ext_ids.get("ArXiv") or paper.get("paperId", "")
            authors = [a.get("name", "") for a in paper.get("authors", [])]
            year = str(paper.get("year", "")) if paper.get("year") else None
            records.append(
                SourceRecord(
                    source=self.name,
                    external_id=external_id,
                    title=paper.get("title") or "",
                    authors=authors,
                    published=year,
                    url=paper.get("url"),
                    raw_excerpt=paper.get("abstract") or "",
                    source_tier=self.source_tier,
                    fetched_at=datetime.now(timezone.utc),
                )
            )
        return records
