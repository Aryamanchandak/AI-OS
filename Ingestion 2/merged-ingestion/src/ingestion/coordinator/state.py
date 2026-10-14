from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from ingestion.coordinator.errors import RunBusyError
from ingestion.coordinator.stages import RunStage, StageStatus


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class StageView:
    stage: RunStage
    status: StageStatus
    detail: Mapping[str, Any]


@dataclass(frozen=True)
class PendingDecision:
    item_id: str
    item_type: str
    gate: str
    adapter: str
    payload: Mapping[str, Any]
    allowed_actions: tuple[str, ...]
    blocking_reason: str


@dataclass(frozen=True)
class ProgressView:
    intake_total: int = 0
    intake_resolved: int = 0
    envelopes_flagged: int = 0
    envelopes_resolved: int = 0


@dataclass(frozen=True)
class ErrorView:
    stage: RunStage
    message: str
    retryable: bool = True


@dataclass(frozen=True)
class RunView:
    run_id: str
    stage: RunStage
    stage_status: StageStatus
    stages: tuple[StageView, ...]
    pending: PendingDecision | None
    progress: ProgressView
    last_error: ErrorView | None
    terminal_result: str | None


@dataclass(frozen=True)
class DecisionRequest:
    run_id: str
    item_id: str
    gate: str
    action: str
    payload: Mapping[str, Any]
    resolver: str
    note: str = ""


@dataclass(frozen=True)
class Publication:
    id: int
    source_path: Path
    note_path: Path
    content_hash: str
    written_at: str
    moved_at: str | None
    moved_to: Path | None
    outcome: str


SCHEMA = """
CREATE TABLE IF NOT EXISTS intake_publications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path TEXT NOT NULL,
  note_path TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  written_at TEXT NOT NULL,
  moved_at TEXT,
  moved_to TEXT,
  outcome TEXT NOT NULL DEFAULT 'published'
);
CREATE INDEX IF NOT EXISTS intake_publications_unfinished
  ON intake_publications (moved_at) WHERE moved_at IS NULL;
"""


class RunStateStore:
    """Publication recovery record and single-process lock."""

    def __init__(self, db_path: Path, run_id: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.db_path.with_suffix(".lock")
        self.run_id = run_id
        with self._connect() as connection:
            connection.executescript(SCHEMA)
        self.acquire_lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def acquire_lock(self) -> None:
        payload = json.dumps({"pid": os.getpid(), "run_id": self.run_id})
        while True:
            try:
                descriptor = os.open(
                    self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                )
            except FileExistsError:
                try:
                    existing = json.loads(self.lock_path.read_text(encoding="utf-8"))
                    pid = int(existing.get("pid", -1))
                except Exception:
                    pid = -1
                if self._pid_alive(pid):
                    raise RunBusyError(
                        f"another coordinator run holds {self.lock_path}"
                    )
                self.lock_path.unlink(missing_ok=True)
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
            return

    def release_lock(self) -> None:
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        if payload.get("run_id") == self.run_id:
            self.lock_path.unlink(missing_ok=True)

    def add_publication(
        self, source_path: Path, note_path: Path, content_hash: str
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO intake_publications
                   (source_path,note_path,content_hash,written_at)
                   VALUES (?,?,?,?)""",
                (str(source_path), str(note_path), content_hash, utc_iso()),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a publication id")
            return int(cursor.lastrowid)

    def unfinished_publication(self) -> Publication | None:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM intake_publications
                   WHERE moved_at IS NULL ORDER BY id"""
            ).fetchall()
        if len(rows) > 1:
            raise RuntimeError("more than one unfinished publication exists")
        if not rows:
            return None
        row = rows[0]
        return Publication(
            id=int(row["id"]),
            source_path=Path(row["source_path"]),
            note_path=Path(row["note_path"]),
            content_hash=str(row["content_hash"]),
            written_at=str(row["written_at"]),
            moved_at=row["moved_at"],
            moved_to=Path(row["moved_to"]) if row["moved_to"] else None,
            outcome=str(row["outcome"]),
        )

    def finish_publication(
        self, publication_id: int, moved_to: Path | None, *, outcome: str = "published"
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE intake_publications
                   SET moved_at=?,moved_to=?,outcome=? WHERE id=?""",
                (utc_iso(), str(moved_to) if moved_to else None, outcome, publication_id),
            )

    def publications(self) -> list[Publication]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM intake_publications ORDER BY id"
            ).fetchall()
        return [
            Publication(
                id=int(row["id"]),
                source_path=Path(row["source_path"]),
                note_path=Path(row["note_path"]),
                content_hash=str(row["content_hash"]),
                written_at=str(row["written_at"]),
                moved_at=row["moved_at"],
                moved_to=Path(row["moved_to"]) if row["moved_to"] else None,
                outcome=str(row["outcome"]),
            )
            for row in rows
        ]
