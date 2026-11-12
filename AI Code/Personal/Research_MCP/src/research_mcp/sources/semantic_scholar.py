"""Semantic Scholar source client.

No API key required (100 req/5min free tier). Set SEMANTIC_SCHOLAR_API_KEY for
10 req/sec (free key at https://www.semanticscholar.org/product/api).
"""
from __future__ import annotations

import os
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ..contracts import Provenance, SourceRecord
from .base import SourceClient

_API_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "paperId,externalIds,title,authors,year,abstract,url"
_USER_AGENT = "ResearchMCP/1.0 (academic research tool)"


def _retry_on_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ReadTimeout):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 503)


class SemanticScholarClient(SourceClient):
    name = "semantic_scholar"

    def __init__(self):
        headers = {"User-Agent": _USER_AGENT}
        api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key
        self._http = httpx.AsyncClient(timeout=30.0, headers=headers)

    @retry(
        retry=retry_if_exception(_retry_on_rate_limit),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def search(self, query: str, **kwargs) -> list[SourceRecord]:
        limit = kwargs.get("limit", 10)
        resp = await self._http.get(
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
                    fetched_at=datetime.utcnow(),
                    provenance=Provenance(
                        query=query,
                        source_tier="academic",
                        fetched_via=self.name,
                    ),
                )
            )
        return records

    async def aclose(self) -> None:
        await self._http.aclose()
