"""arXiv source client (no API key required; uses Atom feed)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ..contracts import SourceRecord
from .base import SourceClient

_API_BASE = "https://export.arxiv.org/api/query"
_HEADERS = {"User-Agent": "ResearchMCP/1.0 (academic research tool)"}
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
_client = httpx.AsyncClient(timeout=30.0, headers=_HEADERS)


def _strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id.strip())


def _extract_arxiv_id(url: str) -> str:
    m = re.search(r"arxiv\.org/abs/([\w./]+)", url)
    return _strip_version(m.group(1)) if m else url


def _retry_on_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ReadTimeout):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 503)


class ArXivClient(SourceClient):
    name = "arxiv"
    source_tier = "preprint"

    @retry(
        retry=retry_if_exception(_retry_on_rate_limit),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def search(self, query: str, **kwargs) -> list[SourceRecord]:
        category = kwargs.get("category")
        search_query = f"all:{query}"
        if category:
            search_query = f"cat:{category} AND all:{query}"

        resp = await _client.get(
            _API_BASE,
            params={"search_query": search_query, "max_results": kwargs.get("limit", 10)},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        records: list[SourceRecord] = []

        for entry in root.findall("atom:entry", _NS):
            id_url = (entry.findtext("atom:id", namespaces=_NS) or "").strip()
            arxiv_id = _extract_arxiv_id(id_url)
            title_el = entry.find("atom:title", _NS)
            title = (title_el.text or "").strip() if title_el is not None else ""
            summary_el = entry.find("atom:summary", _NS)
            abstract = (summary_el.text or "").strip() if summary_el is not None else ""
            authors = [
                (a.findtext("atom:name", namespaces=_NS) or "").strip()
                for a in entry.findall("atom:author", _NS)
            ]
            published_el = entry.find("atom:published", _NS)
            published = (published_el.text or "")[:10] if published_el is not None else None

            records.append(
                SourceRecord(
                    source=self.name,
                    external_id=arxiv_id,
                    title=title,
                    authors=authors,
                    published=published,
                    url=id_url,
                    raw_excerpt=abstract,
                    source_tier=self.source_tier,
                    fetched_at=datetime.now(timezone.utc),
                )
            )
        return records
