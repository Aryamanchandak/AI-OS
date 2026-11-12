"""SQLite persistence for Page Scanner pending review state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from gateway.ingestion.intake.base import IntakeResult


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
  book_meta        TEXT,
  raw_item_id      TEXT,
  raw_bronze_path  TEXT,
  raw_content_hash TEXT,
  raw_processing_path TEXT
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

_MIGRATIONS = {
    "book_meta": "ALTER TABLE pages ADD COLUMN book_meta TEXT",
    "raw_item_id": "ALTER TABLE pages ADD COLUMN raw_item_id TEXT",
    "raw_bronze_path": "ALTER TABLE pages ADD COLUMN raw_bronze_path TEXT",
    "raw_content_hash": "ALTER TABLE pages ADD COLUMN raw_content_hash TEXT",
    "raw_processing_path": "ALTER TABLE pages ADD COLUMN raw_processing_path TEXT",
}


def _connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as connection:
        connection.executescript(SCHEMA)
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(pages)")
        }
        for column, statement in _MIGRATIONS.items():
            if column not in existing:
                connection.execute(statement)


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
    """Insert a page, returning None when its file hash already exists."""

    with _connect(db_path) as connection:
        existing = connection.execute(
            "SELECT id FROM pages WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        if existing:
            return None
        cursor = connection.execute(
            """INSERT INTO pages
               (batch, author, image_path, file_hash, page_number,
                blur_score, glare_score, conf_ratio, status, created_at, book_meta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                batch,
                author,
                image_path,
                file_hash,
                page_number,
                blur_score,
                glare_score,
                conf_ratio,
                status,
                datetime.now(timezone.utc).isoformat(),
                book_meta,
            ),
        )
        return cursor.lastrowid


def insert_passage(
    db_path: str | Path,
    page_id: int,
    *,
    bbox: list[int],
    ocr_text: str,
    edited_text: str | None = None,
    color_tag: str = "yellow",
    min_conf: float | None = None,
) -> int:
    if edited_text is None:
        edited_text = ocr_text
    with _connect(db_path) as connection:
        cursor = connection.execute(
            """INSERT INTO passages
               (page_id, bbox, color_tag, ocr_text, edited_text, min_conf, accepted)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (
                page_id,
                json.dumps(bbox),
                color_tag,
                ocr_text,
                edited_text,
                min_conf,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an id for the passage")
        return cursor.lastrowid


def get_pages(
    db_path: str | Path,
    batch: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM pages"
    clauses: list[str] = []
    parameters: list[Any] = []
    if batch is not None:
        clauses.append("batch = ?")
        parameters.append(batch)
    if status is not None:
        clauses.append("status = ?")
        parameters.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id"
    with _connect(db_path) as connection:
        return [
            dict(row)
            for row in connection.execute(query, parameters).fetchall()
        ]


def get_passages(db_path: str | Path, page_id: int) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM passages WHERE page_id = ? ORDER BY id", (page_id,)
        ).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["bbox"] = json.loads(item["bbox"]) if item["bbox"] else None
        output.append(item)
    return output


def update_passage(
    db_path: str | Path, passage_id: int, edited_text: str
) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE passages SET edited_text = ? WHERE id = ?",
            (edited_text, passage_id),
        )


def update_page_status(db_path: str | Path, page_id: int, status: str) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE pages SET status = ? WHERE id = ?", (status, page_id)
        )


def update_page_number(
    db_path: str | Path, page_id: int, page_number: int | None
) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE pages SET page_number = ? WHERE id = ?",
            (page_number, page_id),
        )


def update_page_author(
    db_path: str | Path, page_id: int, author: str | None
) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE pages SET author = ? WHERE id = ?", (author, page_id)
        )


def get_page(db_path: str | Path, page_id: int) -> dict[str, Any] | None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM pages WHERE id = ?", (page_id,)
        ).fetchone()
    return dict(row) if row else None


def get_page_by_file_hash(
    db_path: str | Path, file_hash: str
) -> dict[str, Any] | None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM pages WHERE file_hash = ?", (file_hash,)
        ).fetchone()
    return dict(row) if row else None


def set_book_meta(
    db_path: str | Path, page_id: int, book_meta: str | None
) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE pages SET book_meta = ? WHERE id = ?", (book_meta, page_id)
        )


def set_image_path(db_path: str | Path, page_id: int, image_path: str) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE pages SET image_path = ? WHERE id = ?", (image_path, page_id)
        )


def rewrite_image_paths_under_folder(
    db_path: str | Path,
    *,
    old_folder: str | Path,
    new_folder: str | Path,
) -> int:
    """Rewrite every stored image path lexically contained by ``old_folder``."""

    old_path = Path(old_folder)
    new_path = Path(new_folder)
    updates: list[tuple[str, int]] = []
    with _connect(db_path) as connection:
        rows = connection.execute("SELECT id, image_path FROM pages").fetchall()
        for row in rows:
            image_path = row["image_path"]
            if not image_path:
                continue
            try:
                relative = Path(str(image_path)).relative_to(old_path)
            except ValueError:
                continue
            updates.append((str(new_path / relative), int(row["id"])))
        connection.executemany(
            "UPDATE pages SET image_path = ? WHERE id = ?", updates
        )
    return len(updates)


def set_raw_publish(
    db_path: str | Path,
    page_id: int,
    *,
    raw_item_id: str,
    raw_bronze_path: str,
    raw_content_hash: str,
) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            """UPDATE pages
               SET raw_item_id = ?, raw_bronze_path = ?, raw_content_hash = ?
               WHERE id = ?""",
            (raw_item_id, raw_bronze_path, raw_content_hash, page_id),
        )


def clear_raw_publish(db_path: str | Path, page_id: int) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            """UPDATE pages
               SET raw_item_id = NULL, raw_bronze_path = NULL,
                   raw_content_hash = NULL
               WHERE id = ?""",
            (page_id,),
        )


def handoff_page_to_processing(
    db_path: str | Path, page_id: int, raw_data_root: str | Path
) -> Path:
    page = get_page(db_path, page_id)
    if not page:
        raise ValueError(f"page {page_id} not found")
    if page.get("raw_processing_path"):
        existing = Path(raw_data_root) / str(page["raw_processing_path"])
        if existing.exists():
            return existing

    processing_root = Path(raw_data_root).expanduser() / "processing"
    processing_root.mkdir(parents=True, exist_ok=True)
    working_path = processing_root / _working_name(Path(str(page["image_path"])))
    working_path.write_text(
        render_processing_markdown(db_path, page_id), encoding="utf-8"
    )
    relative = str(working_path.relative_to(Path(raw_data_root).expanduser()))
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE pages SET raw_processing_path = ? WHERE id = ?",
            (relative, page_id),
        )
    return working_path


def render_processing_markdown(db_path: str | Path, page_id: int) -> str:
    page = get_page(db_path, page_id)
    if not page:
        raise ValueError(f"page {page_id} not found")
    passages = get_passages(db_path, page_id)
    metadata = json.loads(page["book_meta"]) if page.get("book_meta") else {}
    lines = [
        f"# {metadata.get('title') or page.get('batch') or 'Page Scanner capture'}",
        "",
        f"source_image: {page.get('image_path') or ''}",
        f"page_scanner_id: {page['id']}",
        f"page_number: {page.get('page_number') or ''}",
        f"author: {metadata.get('author') or page.get('author') or ''}",
        f"quality_status: {page.get('status') or ''}",
        "",
    ]
    for passage in passages:
        text = str(
            passage.get("edited_text") or passage.get("ocr_text") or ""
        ).strip()
        if text:
            lines.extend((f"> {text}", ""))
    return "\n".join(lines).rstrip() + "\n"


def _working_name(source_path: Path) -> str:
    normalized = str(source_path.expanduser().resolve())
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    safe_stem = "".join(
        character if character.isalnum() else "-"
        for character in source_path.stem.lower()
    ).strip("-")
    return f"{(safe_stem[:60] or 'page-scan')}--{fingerprint}.md"


def park_intake_result(
    db_path: str | Path,
    source_path: Path,
    result: IntakeResult,
    *,
    batch: str | None = None,
    author: str | None = None,
) -> int | None:
    """Persist an approval-bound intake result using the existing schema."""

    init_db(db_path)
    scanner_data = result.frontmatter.get("page_scanner", {})
    if not isinstance(scanner_data, dict):
        scanner_data = {}
    raw_passages = scanner_data.get("passages")
    candidate_passages = raw_passages if isinstance(raw_passages, list) else []
    if not candidate_passages:
        candidate_passages = [
            {
                "text": result.markdown_text,
                "edited_text": result.markdown_text,
                "bbox": [],
                "min_conf": None,
            }
        ]

    passages: list[dict[str, Any]] = []
    for passage in candidate_passages:
        if not isinstance(passage, dict):
            raise TypeError("page_scanner passages must be dictionaries")
        bbox = passage.get("bbox", [])
        if not isinstance(bbox, list) or not all(
            isinstance(value, int) for value in bbox
        ):
            raise TypeError("page_scanner passage bbox must contain integers")
        passages.append(passage)

    digest = scanner_data.get("file_hash")
    if not isinstance(digest, str) or not digest:
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    flagged_retake = bool(scanner_data.get("flagged_retake", False))
    book_meta = result.frontmatter.get("book_meta", {})
    page_id = insert_page(
        db_path,
        batch=batch or result.title,
        author=author,
        image_path=str(source_path),
        file_hash=digest,
        status="retake" if flagged_retake else "new",
        blur_score=_optional_float(scanner_data.get("blur_score")),
        glare_score=_optional_float(scanner_data.get("glare_score")),
        conf_ratio=_optional_float(scanner_data.get("conf_ratio")),
        book_meta=json.dumps(book_meta, ensure_ascii=False),
    )
    if page_id is None:
        return None

    for passage in passages:
        bbox = passage.get("bbox", [])
        insert_passage(
            db_path,
            page_id,
            bbox=bbox,
            ocr_text=str(passage.get("text", "")),
            edited_text=str(
                passage.get("edited_text", passage.get("text", ""))
            ),
            min_conf=_optional_float(passage.get("min_conf")),
        )
    if flagged_retake:
        _move_retake_photo(db_path, page_id, source_path)
    return page_id


def mark_retake(db_path: str | Path, page_id: int, source_path: Path) -> Path:
    """Move one photo into its folder's `_retake/` and record the new path."""

    return _move_retake_photo(db_path, page_id, source_path)


def restore_from_retake(
    db_path: str | Path, page_id: int, source_path: Path
) -> Path:
    """Move an approved photo back out of `_retake/` and record where it went."""

    source_path = Path(source_path)
    if source_path.parent.name != "_retake":
        return source_path
    destination = _available_destination(
        source_path.parent.parent / source_path.name
    )
    shutil.move(str(source_path), destination)
    try:
        set_image_path(db_path, page_id, str(destination))
    except Exception:
        try:
            shutil.move(str(destination), source_path)
        except Exception as rollback_error:
            raise RuntimeError(
                "approved-photo path update failed and the move out of "
                "_retake could not be rolled back"
            ) from rollback_error
        raise
    return destination


def _move_retake_photo(
    db_path: str | Path, page_id: int, source_path: Path
) -> Path:
    """Move one RETAKE photo and compensate if its path update fails."""

    if source_path.parent.name == "_retake":
        set_image_path(db_path, page_id, str(source_path))
        return source_path

    retake_folder = source_path.parent / "_retake"
    retake_folder.mkdir(parents=True, exist_ok=True)
    destination = _available_destination(retake_folder / source_path.name)
    shutil.move(str(source_path), destination)
    try:
        set_image_path(db_path, page_id, str(destination))
    except Exception:
        try:
            shutil.move(str(destination), source_path)
        except Exception as rollback_error:
            raise RuntimeError(
                "RETAKE path update failed and the photo move could not be "
                "rolled back"
            ) from rollback_error
        raise
    return destination


def _available_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    counter = 2
    while True:
        candidate = destination.with_name(
            f"{destination.stem}-{counter}{destination.suffix}"
        )
        if not candidate.exists():
            return candidate
        counter += 1


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


@dataclass(frozen=True)
class PendingReviewStore:
    """Callable adapter for `run_funnel(..., park_for_review=...)`."""

    db_path: Path
    batch: str | None = None
    author: str | None = None

    def __call__(self, source: Path, result: IntakeResult) -> int | None:
        return park_intake_result(
            self.db_path,
            source,
            result,
            batch=self.batch,
            author=self.author,
        )
