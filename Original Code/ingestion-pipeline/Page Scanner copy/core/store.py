# Agent guide: Owns the SQLite schema and all page, passage, review, deduplication, and handoff persistence operations.
"""SQLite persistence (schema = spec §4). stdlib sqlite3, no ORM.

The DB is fully regenerable from the photos *except* edited_text. Re-running the
inbox is idempotent via pages.file_hash UNIQUE.
"""

from __future__ import annotations

import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
  id            INTEGER PRIMARY KEY,
  batch         TEXT,
  author        TEXT,
  image_path    TEXT,
  file_hash     TEXT UNIQUE,
  page_number   INTEGER,
  blur_score    REAL,
  glare_score   REAL,
  conf_ratio    REAL,
  status        TEXT,
  created_at    TEXT,
  book_meta        TEXT,   -- JSON: resolved title/author/year/isbn/subjects
  raw_item_id      TEXT,   -- stable id of the published Raw Data bronze item
  raw_bronze_path  TEXT,   -- rel path of that item (reused on re-accept)
  raw_content_hash TEXT,   -- content hash last published (skip no-op re-writes)
  raw_processing_path TEXT -- rel path of the mutable Raw Data/processing handoff
);

CREATE TABLE IF NOT EXISTS passages (
  id            INTEGER PRIMARY KEY,
  page_id       INTEGER REFERENCES pages(id),
  bbox          TEXT,
  color_tag     TEXT,
  ocr_text      TEXT,
  edited_text   TEXT,
  min_conf      REAL,
  accepted      INTEGER DEFAULT 0
);
"""

# Columns added after the original schema shipped. init_db() adds any that are
# missing so an existing processed.db upgrades in place (sqlite has no
# ADD COLUMN IF NOT EXISTS, hence the introspection).
_MIGRATIONS = {
    "book_meta": "ALTER TABLE pages ADD COLUMN book_meta TEXT",
    "raw_item_id": "ALTER TABLE pages ADD COLUMN raw_item_id TEXT",
    "raw_bronze_path": "ALTER TABLE pages ADD COLUMN raw_bronze_path TEXT",
    "raw_content_hash": "ALTER TABLE pages ADD COLUMN raw_content_hash TEXT",
    "raw_processing_path": "ALTER TABLE pages ADD COLUMN raw_processing_path TEXT",
}


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path) -> None:
    """Create tables if they don't exist, then apply column migrations."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(pages)")}
        for col, ddl in _MIGRATIONS.items():
            if col not in existing:
                conn.execute(ddl)


def insert_page(
    db_path: str | Path,
    *,
    batch: str,
    author: str | None,
    image_path: str,
    file_hash: str,
    status: str = "new",
    page_number: int | None = None,
    blur_score: float | None = None,
    glare_score: float | None = None,
    conf_ratio: float | None = None,
    book_meta: str | None = None,
) -> int | None:
    """Insert a page row → page_id. Returns None if file_hash already exists
    (idempotent skip of the whole image)."""
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM pages WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        if existing:
            return None
        cur = conn.execute(
            """INSERT INTO pages
               (batch, author, image_path, file_hash, page_number,
                blur_score, glare_score, conf_ratio, status, created_at, book_meta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                batch, author, image_path, file_hash, page_number,
                blur_score, glare_score, conf_ratio, status,
                datetime.now(timezone.utc).isoformat(), book_meta,
            ),
        )
        return cur.lastrowid


def insert_passage(
    db_path: str | Path,
    page_id: int,
    *,
    bbox: list,
    ocr_text: str,
    edited_text: str | None = None,
    color_tag: str = "yellow",
    min_conf: float | None = None,
) -> int:
    """Insert a passage row. edited_text defaults to ocr_text."""
    if edited_text is None:
        edited_text = ocr_text
    with _connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO passages
               (page_id, bbox, color_tag, ocr_text, edited_text, min_conf, accepted)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (page_id, json.dumps(bbox), color_tag, ocr_text, edited_text, min_conf),
        )
        return cur.lastrowid


def get_pages(
    db_path: str | Path,
    batch: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List pages, optionally filtered by batch and/or status, ordered by id."""
    q = "SELECT * FROM pages"
    clauses, params = [], []
    if batch is not None:
        clauses.append("batch = ?")
        params.append(batch)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY id"
    with _connect(db_path) as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_passages(db_path: str | Path, page_id: int) -> list[dict]:
    """Passages for a page, ordered by id. bbox is decoded from JSON."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM passages WHERE page_id = ? ORDER BY id", (page_id,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["bbox"] = json.loads(d["bbox"]) if d["bbox"] else None
        out.append(d)
    return out


def update_passage(db_path: str | Path, passage_id: int, edited_text: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE passages SET edited_text = ? WHERE id = ?",
            (edited_text, passage_id),
        )


def update_page_status(db_path: str | Path, page_id: int, status: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE pages SET status = ? WHERE id = ?", (status, page_id)
        )


def update_page_number(db_path: str | Path, page_id: int, page_number: int | None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE pages SET page_number = ? WHERE id = ?", (page_number, page_id)
        )


def update_page_author(db_path: str | Path, page_id: int, author: str | None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE pages SET author = ? WHERE id = ?", (author, page_id)
        )


def get_page(db_path: str | Path, page_id: int) -> dict | None:
    """One page row as a dict, or None. Cheaper than get_pages()+linear scan."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    return dict(row) if row else None


def get_page_by_file_hash(db_path: str | Path, file_hash: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM pages WHERE file_hash = ?", (file_hash,)
        ).fetchone()
    return dict(row) if row else None


def set_book_meta(db_path: str | Path, page_id: int, book_meta: str | None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE pages SET book_meta = ? WHERE id = ?", (book_meta, page_id)
        )


def set_image_path(db_path: str | Path, page_id: int, image_path: str) -> None:
    """Repoint a page at its image's new home (after the move into Raw Data), so
    the cockpit still serves it on editable back-navigation."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE pages SET image_path = ? WHERE id = ?", (image_path, page_id)
        )


def set_raw_publish(
    db_path: str | Path,
    page_id: int,
    *,
    raw_item_id: str,
    raw_bronze_path: str,
    raw_content_hash: str,
) -> None:
    """Record where/what this page was last published into the Raw Data lake, so a
    re-accept reuses the same item id + path and skips a no-op re-write."""
    with _connect(db_path) as conn:
        conn.execute(
            """UPDATE pages
               SET raw_item_id = ?, raw_bronze_path = ?, raw_content_hash = ?
               WHERE id = ?""",
            (raw_item_id, raw_bronze_path, raw_content_hash, page_id),
        )


def clear_raw_publish(db_path: str | Path, page_id: int) -> None:
    """Forget a page's Raw Data publish state (after unpublish on discard/retake)."""
    with _connect(db_path) as conn:
        conn.execute(
            """UPDATE pages
               SET raw_item_id = NULL, raw_bronze_path = NULL, raw_content_hash = NULL
               WHERE id = ?""",
            (page_id,),
        )


def handoff_page_to_processing(
    db_path: str | Path,
    page_id: int,
    raw_data_root: str | Path,
) -> Path:
    """Write the OCR candidate into Raw Data/processing as mutable pre-bronze."""
    page = get_page(db_path, page_id)
    if not page:
        raise ValueError(f"page {page_id} not found")
    if page.get("raw_processing_path"):
        existing = Path(raw_data_root) / page["raw_processing_path"]
        if existing.exists():
            return existing

    processing_root = Path(raw_data_root).expanduser() / "processing"
    processing_root.mkdir(parents=True, exist_ok=True)
    working_path = processing_root / _working_name(Path(page["image_path"]))
    working_path.write_text(render_processing_markdown(db_path, page_id), encoding="utf-8")

    rel = str(working_path.relative_to(Path(raw_data_root).expanduser()))
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE pages SET raw_processing_path = ? WHERE id = ?",
            (rel, page_id),
        )
    return working_path


def render_processing_markdown(db_path: str | Path, page_id: int) -> str:
    page = get_page(db_path, page_id)
    if not page:
        raise ValueError(f"page {page_id} not found")
    passages = get_passages(db_path, page_id)
    meta = json.loads(page["book_meta"]) if page.get("book_meta") else {}

    lines = [
        f"# {meta.get('title') or page.get('batch') or 'Page Scanner capture'}",
        "",
        f"source_image: {page.get('image_path') or ''}",
        f"page_scanner_id: {page['id']}",
        f"page_number: {page.get('page_number') or ''}",
        f"author: {meta.get('author') or page.get('author') or ''}",
        f"quality_status: {page.get('status') or ''}",
        "",
    ]
    for passage in passages:
        text = (passage.get("edited_text") or passage.get("ocr_text") or "").strip()
        if text:
            lines.append(f"> {text}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _working_name(source_path: Path) -> str:
    normalized = str(source_path.expanduser().resolve())
    path_fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    stem = source_path.stem.lower()
    safe_stem = "".join(char if char.isalnum() else "-" for char in stem).strip("-")
    safe_stem = safe_stem[:60] or "page-scan"
    return f"{safe_stem}--{path_fingerprint}.md"
