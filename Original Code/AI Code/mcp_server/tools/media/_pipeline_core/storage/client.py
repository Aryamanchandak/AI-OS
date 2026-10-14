"""SQLite access layer for operational podcast state."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from tools.media._pipeline_core.shared.contracts import (
    ArtifactRow,
    ClaimRow,
    EpisodeRow,
    RunRow,
    ToolExecutionRow,
)

DEFAULT_DB_PATH = Path("/Users/aryamanchandak/Documents/AI Code/Database/sqlite/podcast_pipeline.db")
_STORE: SQLiteStateStore | None = None


class SQLiteStateStore:
    """Persistence layer for podcast episode state and related records."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or _resolve_db_path()
        self._schema_path = Path(__file__).with_name("schema.sql")

    def ensure_database(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        schema = self._schema_path.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema)

    def upsert_episode(self, row: EpisodeRow) -> None:
        self.ensure_database()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes (
                    episode_id, show_name, title, source_url, profile, status
                ) VALUES (
                    :episode_id, :show_name, :title, :source_url, :profile, :status
                )
                ON CONFLICT(episode_id) DO UPDATE SET
                    show_name = excluded.show_name,
                    title = excluded.title,
                    source_url = excluded.source_url,
                    profile = excluded.profile,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                row.model_dump(),
            )

    def log_run(self, row: RunRow) -> None:
        self.ensure_database()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (episode_id, stage, status, message)
                VALUES (:episode_id, :stage, :status, :message)
                """,
                row.model_dump(),
            )

    def save_artifact(self, row: ArtifactRow) -> None:
        self.ensure_database()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO artifacts (episode_id, artifact_type, artifact_path)
                VALUES (:episode_id, :artifact_type, :artifact_path)
                """,
                row.model_dump(),
            )

    def upsert_claim(self, row: ClaimRow) -> None:
        self.ensure_database()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO claims (claim_id, episode_id, claim_type, quote, summary)
                VALUES (:claim_id, :episode_id, :claim_type, :quote, :summary)
                ON CONFLICT(claim_id) DO UPDATE SET
                    episode_id = excluded.episode_id,
                    claim_type = excluded.claim_type,
                    quote = excluded.quote,
                    summary = excluded.summary
                """,
                row.model_dump(),
            )

    def log_tool_execution(self, row: ToolExecutionRow) -> None:
        self.ensure_database()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tool_executions (tool_name, episode_id, status, message)
                VALUES (:tool_name, :episode_id, :status, :message)
                """,
                row.model_dump(),
            )

    def get_episode(self, episode_id: str) -> dict[str, Any] | None:
        self.ensure_database()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT episode_id, show_name, title, source_url, profile, status,
                       created_at, updated_at
                FROM episodes
                WHERE episode_id = ?
                """,
                (episode_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_runs(self, episode_id: str) -> list[dict[str, Any]]:
        self.ensure_database()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, episode_id, stage, status, message, started_at
                FROM runs
                WHERE episode_id = ?
                ORDER BY id ASC
                """,
                (episode_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_claims(self, episode_id: str) -> list[dict[str, Any]]:
        self.ensure_database()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT claim_id, episode_id, claim_type, quote, summary, created_at
                FROM claims
                WHERE episode_id = ?
                ORDER BY created_at ASC, claim_id ASC
                """,
                (episode_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn


def _resolve_db_path() -> Path:
    return Path(os.getenv("PODCAST_DB_PATH", str(DEFAULT_DB_PATH)))


def get_store() -> SQLiteStateStore:
    global _STORE
    if _STORE is None:
        _STORE = SQLiteStateStore()
    return _STORE
