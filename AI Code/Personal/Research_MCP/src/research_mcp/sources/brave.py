"""Brave Search source client (requires BRAVE_API_KEY env var)."""
from __future__ import annotations

import os
from datetime import datetime
from urllib.parse import urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..contracts import Provenance, SourceRecord
from ..trusted_sources import TrustedSources, load_trusted_sources
from .base import SourceClient, SourceUnavailableError

_API_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveClient(SourceClient):
    name = "brave"

    def __init__(self, trusted: TrustedSources | None = None):
        key = os.environ.get("BRAVE_API_KEY")
        if not key:
            raise SourceUnavailableError("BRAVE_API_KEY not set")
        self._key = key
        self._trusted = trusted or load_trusted_sources()
        self._http = httpx.AsyncClient(timeout=30.0)

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def search(self, query: str, **kwargs) -> list[SourceRecord]:
        trusted_only: bool | None = kwargs.get("trusted_sources_only")
        category: str | None = kwargs.get("category")
        limit = kwargs.get("limit", 10)

        params: dict = {"q": query, "count": limit}
        if trusted_only:
            domains = self._trusted.get_domains(category)
            if domains:
                # Brave supports site: filter; build OR query
                site_filter = " OR ".join(f"site:{d}" for d in domains[:10])
                params["q"] = f"({query}) ({site_filter})"

        resp = await self._http.get(
            _API_URL,
            headers={"Accept": "application/json", "X-Subscription-Token": self._key},
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        records: list[SourceRecord] = []
        for item in data.get("web", {}).get("results", []):
            url = item.get("url", "")
            tier = self._trusted.get_tier(url) if url else "open_web"
            records.append(
                SourceRecord(
                    source=self.name,
                    external_id=url,
                    title=item.get("title") or "",
                    authors=[],
                    published=item.get("page_age"),
                    url=url,
                    raw_excerpt=item.get("description") or "",
                    fetched_at=datetime.utcnow(),
                    provenance=Provenance(
                        query=query,
                        source_tier=tier,
                        fetched_via=self.name,
                    ),
                )
            )
        return records

    async def aclose(self) -> None:
        await self._http.aclose()
