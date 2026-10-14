"""Abbreviation mapping repository and append-only cleanup audit log.

Two SQLite-backed concerns live here because they share a database and, for
Apply + remember, a single transaction (component_8.md section 7.5: "Apply +
remember must write the mapping and its decision-log row in one SQLite
transaction"). Nothing in v1 queries the audit log back for anything other
than human reading -- it is never used to resume, skip, reopen, or decide
completion (C8-C8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid

from ingestion.text_cleanup.abbreviations import MappingRow

SCHEMA = """
CREATE TABLE IF NOT EXISTS cleanup_mappings (
  id TEXT PRIMARY KEY,
  shorthand TEXT NOT NULL,
  expansion TEXT NOT NULL,
  case_sensitive INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS cleanup_mappings_active_unique
  ON cleanup_mappings (shorthand, case_sensitive)
  WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS cleanup_audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_kind TEXT NOT NULL,
  run_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  occurrence_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  action TEXT NOT NULL,
  before TEXT NOT NULL,
  after TEXT NOT NULL,
  interaction_revision INTEGER NOT NULL,
  working_draft_revision INTEGER NOT NULL,
  at TEXT NOT NULL
);
"""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: str | Path) -> None:
    with _connect(db_path) as connection:
        connection.executescript(SCHEMA)


@dataclass(frozen=True)
class MappingRecord:
    id: str
    shorthand: str
    expansion: str
    case_sensitive: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class AuditEntry:
    source_kind: str
    run_id: str
    item_id: str
    occurrence_id: str
    phase: str
    action: str
    before: str
    after: str
    interaction_revision: int
    working_draft_revision: int


def _row_to_record(row: sqlite3.Row) -> MappingRecord:
    return MappingRecord(
        id=str(row["id"]),
        shorthand=str(row["shorthand"]),
        expansion=str(row["expansion"]),
        case_sensitive=bool(row["case_sensitive"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class DuplicateMappingError(ValueError):
    pass


class MappingNotFoundError(KeyError):
    pass


class MappingRepository:
    """Abbreviation mappings plus the write-only cleanup audit log.

    One repository per ``text_cleanup.db`` path; safe to construct more than
    once against the same file (schema creation is idempotent).
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        init_db(self.db_path)

    def active_mappings(self) -> list[MappingRow]:
        with _connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM cleanup_mappings WHERE deleted_at IS NULL ORDER BY shorthand"
            ).fetchall()
        return [
            MappingRow(
                id=str(row["id"]),
                shorthand=str(row["shorthand"]),
                expansion=str(row["expansion"]),
                case_sensitive=bool(row["case_sensitive"]),
            )
            for row in rows
        ]

    def search(self, query: str) -> list[MappingRecord]:
        with _connect(self.db_path) as connection:
            rows = connection.execute(
                """SELECT * FROM cleanup_mappings
                   WHERE deleted_at IS NULL AND shorthand LIKE ?
                   ORDER BY shorthand""",
                (f"%{query}%",),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def get(self, mapping_id: str) -> MappingRecord | None:
        with _connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM cleanup_mappings WHERE id = ? AND deleted_at IS NULL",
                (mapping_id,),
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    def create(
        self, shorthand: str, expansion: str, *, case_sensitive: bool = True
    ) -> MappingRecord:
        if not shorthand.strip():
            raise ValueError("shorthand cannot be blank")
        if not expansion.strip():
            raise ValueError("expansion cannot be blank")
        mapping_id = uuid.uuid4().hex
        now = _utc_iso()
        try:
            with _connect(self.db_path) as connection:
                connection.execute(
                    """INSERT INTO cleanup_mappings
                       (id, shorthand, expansion, case_sensitive, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (mapping_id, shorthand, expansion, int(case_sensitive), now, now),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateMappingError(
                f"an active mapping already exists for {shorthand!r} "
                f"(case_sensitive={case_sensitive})"
            ) from error
        record = self.get(mapping_id)
        assert record is not None
        return record

    def edit(self, mapping_id: str, *, expansion: str) -> MappingRecord:
        if not expansion.strip():
            raise ValueError("expansion cannot be blank")
        with _connect(self.db_path) as connection:
            cursor = connection.execute(
                """UPDATE cleanup_mappings SET expansion = ?, updated_at = ?
                   WHERE id = ? AND deleted_at IS NULL""",
                (expansion, _utc_iso(), mapping_id),
            )
            if cursor.rowcount == 0:
                raise MappingNotFoundError(mapping_id)
        record = self.get(mapping_id)
        assert record is not None
        return record

    def delete(self, mapping_id: str) -> None:
        with _connect(self.db_path) as connection:
            cursor = connection.execute(
                """UPDATE cleanup_mappings SET deleted_at = ?
                   WHERE id = ? AND deleted_at IS NULL""",
                (_utc_iso(), mapping_id),
            )
            if cursor.rowcount == 0:
                raise MappingNotFoundError(mapping_id)

    def append_audit(self, entry: AuditEntry) -> None:
        with _connect(self.db_path) as connection:
            self._insert_audit(connection, entry)

    @staticmethod
    def _insert_audit(connection: sqlite3.Connection, entry: AuditEntry) -> None:
        connection.execute(
            """INSERT INTO cleanup_audit_log
               (source_kind, run_id, item_id, occurrence_id, phase, action,
                before, after, interaction_revision, working_draft_revision, at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.source_kind,
                entry.run_id,
                entry.item_id,
                entry.occurrence_id,
                entry.phase,
                entry.action,
                entry.before,
                entry.after,
                entry.interaction_revision,
                entry.working_draft_revision,
                _utc_iso(),
            ),
        )

    def record_apply_remember(
        self,
        *,
        shorthand: str,
        expansion: str,
        case_sensitive: bool,
        audit: AuditEntry,
    ) -> MappingRecord:
        """Create-or-update the mapping and append its audit row atomically.

        One active row per shorthand+case policy: editing an existing active
        mapping replaces its expansion rather than creating a second
        contradictory active row (section 6.2).
        """

        if not shorthand.strip():
            raise ValueError("shorthand cannot be blank")
        if not expansion.strip():
            raise ValueError("expansion cannot be blank")
        now = _utc_iso()
        with _connect(self.db_path) as connection:
            existing = connection.execute(
                """SELECT id FROM cleanup_mappings
                   WHERE shorthand = ? AND case_sensitive = ? AND deleted_at IS NULL""",
                (shorthand, int(case_sensitive)),
            ).fetchone()
            if existing is not None:
                mapping_id = str(existing["id"])
                connection.execute(
                    "UPDATE cleanup_mappings SET expansion = ?, updated_at = ? WHERE id = ?",
                    (expansion, now, mapping_id),
                )
            else:
                mapping_id = uuid.uuid4().hex
                connection.execute(
                    """INSERT INTO cleanup_mappings
                       (id, shorthand, expansion, case_sensitive, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (mapping_id, shorthand, expansion, int(case_sensitive), now, now),
                )
            self._insert_audit(connection, audit)
            row = connection.execute(
                "SELECT * FROM cleanup_mappings WHERE id = ?", (mapping_id,)
            ).fetchone()
        assert row is not None
        return _row_to_record(row)
