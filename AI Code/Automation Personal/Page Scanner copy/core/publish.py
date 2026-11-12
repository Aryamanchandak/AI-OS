"""Commit a reviewed Page Scanner page through Raw Data capture().

The scanner keeps OCR/detect/quality state in processed.db and hands a mutable
markdown candidate to Raw Data/processing. Bronze is written only by
lib.capture.capture(); this module never writes, rewrites, unlocks, or deletes
bronze files.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from core import settings, store

os.environ.setdefault("RAW_DATA_ROOT", str(settings.RAW_DATA_ROOT))
if str(settings.RAW_DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(settings.RAW_DATA_ROOT))

from lib.capture import capture  # noqa: E402
from lib.ledger import init_ledger  # noqa: E402

RAW_ROOT = settings.RAW_DATA_ROOT
SOURCE = settings.RAW_SOURCE


def publish_page(db_path: str | Path, page_id: int) -> dict:
    """Capture one reviewed scan once, permanently."""
    page = store.get_page(db_path, page_id)
    if not page:
        raise ValueError(f"page {page_id} not found")

    if page.get("raw_content_hash") and page.get("raw_bronze_path"):
        return {
            "published": False,
            "reason": "already-captured",
            "page_id": page_id,
            "item_id": page.get("raw_item_id"),
            "bronze_path": page.get("raw_bronze_path"),
        }

    processing_path = store.handoff_page_to_processing(db_path, page_id, RAW_ROOT)
    body = processing_path.read_text(encoding="utf-8")
    if not body.strip():
        return {"published": False, "reason": "empty", "page_id": page_id}

    init_ledger()
    result = capture(
        source=SOURCE,
        content=body,
        metadata=_metadata(page),
        authored=False,
    )
    bronze_path = (
        str(Path(result.path).relative_to(RAW_ROOT))
        if result.path
        else page.get("raw_bronze_path")
    )
    store.set_raw_publish(
        db_path,
        page_id,
        raw_item_id=result.item_id,
        raw_bronze_path=bronze_path or "",
        raw_content_hash=result.content_hash,
    )
    return {
        "published": not result.duplicate,
        "duplicate": result.duplicate,
        "page_id": page_id,
        "item_id": result.item_id,
        "content_hash": result.content_hash,
        "bronze_path": bronze_path,
        "processing_path": str(processing_path.relative_to(RAW_ROOT)),
    }


def unpublish_page(db_path: str | Path, page_id: int) -> dict:
    """Bronze captures are immutable; non-reviewed saves do not delete them."""
    page = store.get_page(db_path, page_id)
    if not page or not page.get("raw_content_hash"):
        return {"unpublished": False, "reason": "not-published", "page_id": page_id}
    return {
        "unpublished": False,
        "reason": "immutable-capture",
        "page_id": page_id,
        "item_id": page.get("raw_item_id"),
        "bronze_path": page.get("raw_bronze_path"),
    }


def _metadata(page: dict) -> dict:
    meta = json.loads(page["book_meta"]) if page.get("book_meta") else {}
    subjects = meta.get("subjects")
    if isinstance(subjects, list):
        subjects = ", ".join(str(item) for item in subjects)
    return {
        "title": meta.get("title") or page.get("batch") or "",
        "author": meta.get("author") or page.get("author") or "",
        "year": meta.get("year") or "",
        "isbn": meta.get("isbn") or "",
        "subjects": subjects or "",
        "page_number": page.get("page_number") or "",
        "batch": page.get("batch") or "",
        "source_image": page.get("image_path") or "",
        "page_scanner_id": page.get("id") or "",
        "file_hash": page.get("file_hash") or "",
        "meta_source": meta.get("meta_source") or "",
        "meta_confidence": meta.get("confidence") or "",
    }
