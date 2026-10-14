from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Protocol

from .models import IterationUsage


class IterationRecorder(Protocol):
    def record(self, request_id: str, iteration: IterationUsage) -> None: ...


class SQLiteIterationStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS advisor_iterations (
                    request_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('executor', 'advisor')),
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cache_read_tokens INTEGER NOT NULL,
                    cache_write_tokens INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (request_id, ordinal)
                )
                """
            )

    def record(self, request_id: str, iteration: IterationUsage) -> None:
        usage = iteration.usage
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO advisor_iterations (
                    request_id, ordinal, role, model, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    iteration.ordinal,
                    iteration.role,
                    iteration.model,
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.cache_read_tokens,
                    usage.cache_write_tokens,
                ),
            )

    def fetch(self, request_id: str) -> tuple[IterationUsage, ...]:
        from .models import TokenUsage

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT ordinal, role, model, input_tokens, output_tokens,
                       cache_read_tokens, cache_write_tokens
                FROM advisor_iterations
                WHERE request_id = ?
                ORDER BY ordinal
                """,
                (request_id,),
            ).fetchall()
        return tuple(
            IterationUsage(
                ordinal=row[0],
                role=row[1],
                model=row[2],
                usage=TokenUsage(
                    input_tokens=row[3],
                    output_tokens=row[4],
                    cache_read_tokens=row[5],
                    cache_write_tokens=row[6],
                ),
            )
            for row in rows
        )
