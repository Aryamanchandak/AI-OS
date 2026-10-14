from __future__ import annotations

import hashlib
from urllib.parse import urlsplit

from ..models import DiscoveryExtract, NewsBatch, NewsItem
from ..providers.fetch import PageFetcher, UnsafeUrl, normalize_url


def stable_item_id(url: str) -> str:
    return "N" + hashlib.sha256(url.encode()).hexdigest()[:12].upper()


def normalize_batch(batch: NewsBatch) -> NewsBatch:
    items, seen = [], set()
    for item in batch.items:
        canonical = normalize_url(str(item.url))
        if canonical in seen:
            continue
        seen.add(canonical)
        data = item.model_dump()
        data["url"] = canonical
        # Upstream IDs are metadata, not trusted internal keys. The canonical
        # URL determines a stable ID across batches and restarts.
        data["id"] = stable_item_id(canonical)
        items.append(NewsItem.model_validate(data))
    return NewsBatch(batch_id=batch.batch_id, items=items, target_market=batch.target_market, report_audience=batch.report_audience, requested_at=batch.requested_at)


def pre_read(batch: NewsBatch, fetcher: PageFetcher, max_chars: int = 8000, guard=lambda: None) -> list[DiscoveryExtract]:
    extracts: list[DiscoveryExtract] = []
    for item in batch.items:
        guard()
        item_id = item.id or stable_item_id(str(item.url))
        canonical = normalize_url(str(item.url))
        supplied = "\n\n".join(p for p in (item.headline, item.snippet) if p)
        if item.headline and item.snippet and len(supplied) >= 240:
            extracts.append(DiscoveryExtract(item_id=item_id, canonical_url=canonical, headline=item.headline, publisher=item.publisher, published_at=item.published_at, text=supplied[:max_chars], fetched=False))
            continue
        try:
            result = fetcher.fetch(canonical)
            text = "\n\n".join(p for p in (supplied, result.text) if p)[:max_chars]
            extracts.append(DiscoveryExtract(item_id=item_id, canonical_url=canonical, headline=item.headline or result.title, publisher=item.publisher or urlsplit(canonical).hostname, published_at=item.published_at, text=text, fetched=True))
        except Exception as exc:
            extracts.append(DiscoveryExtract(item_id=item_id, canonical_url=canonical, headline=item.headline, publisher=item.publisher, published_at=item.published_at, text=supplied[:max_chars], fetched=False, failure_reason=str(exc)))
    return extracts
