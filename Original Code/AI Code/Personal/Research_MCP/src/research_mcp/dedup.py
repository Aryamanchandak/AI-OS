"""Fingerprinting and logical-source deduplication (§9).

Pipeline:
  1. normalize_id — canonical form per source
  2. content_fingerprint — hash(normalize(title) + first_author + year)
  3. merge_into_logical_sources — group SourceRecords → LogicalSources
  4. check_existing — sources table first, before any API call
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from .contracts import LogicalSource, SourceRecord


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"[\s\-–—]+", " ", text).strip()
    return text


def normalize_id(source: str, external_id: str) -> str:
    """Return canonical form of an external ID."""
    if source == "arxiv":
        # Strip version suffix: 2301.01234v2 → 2301.01234
        return re.sub(r"v\d+$", "", external_id.strip().lower())
    if source == "semantic_scholar":
        # DOI: lowercase, strip leading doi.org prefix
        eid = external_id.lower()
        eid = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", eid)
        return eid
    if source in ("brave", "wikipedia", "google_books"):
        # Strip URL tracking params
        try:
            parsed = urlparse(external_id)
            clean_qs = {k: v for k, v in parse_qs(parsed.query).items() if k not in ("utm_source", "utm_medium", "utm_campaign", "ref")}
            cleaned = parsed._replace(query=urlencode(clean_qs, doseq=True))
            return urlunparse(cleaned).rstrip("/")
        except Exception:
            return external_id
    return external_id.strip().lower()


def content_fingerprint(title: str, first_author: str, year: str | None) -> str:
    """SHA-256 of normalize(title)+first_author+year. Catches no-shared-ID case."""
    key = _normalize_text(title) + "|" + _normalize_text(first_author) + "|" + (year or "")
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _record_fingerprint(record: SourceRecord) -> str:
    first_author = record.authors[0] if record.authors else ""
    year = (record.published or "")[:4]
    return content_fingerprint(record.title, first_author, year)


def merge_into_logical_sources(records: list[SourceRecord]) -> list[LogicalSource]:
    """Collapse duplicate SourceRecords → distinct LogicalSources."""
    fp_to_ls: dict[str, LogicalSource] = {}

    for rec in records:
        fp = _record_fingerprint(rec)
        if fp in fp_to_ls:
            ls = fp_to_ls[fp]
            ls.external_ids[rec.source] = normalize_id(rec.source, rec.external_id)
            ls.provenance.append(rec.provenance)
            if not ls.raw_excerpt and rec.raw_excerpt:
                ls.raw_excerpt = rec.raw_excerpt
            if not ls.url and rec.url:
                ls.url = rec.url
        else:
            ls = LogicalSource(
                fingerprint=fp,
                external_ids={rec.source: normalize_id(rec.source, rec.external_id)},
                title=rec.title,
                authors=rec.authors,
                published=rec.published,
                url=rec.url,
                raw_excerpt=rec.raw_excerpt,
                provenance=[rec.provenance],
            )
            fp_to_ls[fp] = ls

    return list(fp_to_ls.values())


async def check_existing(db_path: str, fingerprints: list[str]) -> dict[str, str]:
    """Return {fingerprint: logical_source_id} for records already in the DB."""
    from .database import get_existing_fingerprints
    return await get_existing_fingerprints(db_path, fingerprints)


def compute_fingerprints(records: list[SourceRecord]) -> dict[str, str]:
    """Return {fingerprint: record.external_id} for a batch of SourceRecords."""
    return {_record_fingerprint(r): r.external_id for r in records}
