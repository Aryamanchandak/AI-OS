from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .models import Decision, Event


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_parts(*parts: str | None) -> str:
    material = "\n".join(part or "" for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class SQLiteEventStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    prev_event_hash TEXT,
                    event_hash TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decision_sequences (
                    year INTEGER PRIMARY KEY,
                    last_value INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS commit_chain (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    head_hash TEXT
                );

                INSERT OR IGNORE INTO commit_chain(singleton, head_hash) VALUES (1, NULL);

                CREATE TRIGGER IF NOT EXISTS events_no_update
                BEFORE UPDATE ON events
                BEGIN
                    SELECT RAISE(ABORT, 'events are append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS events_no_delete
                BEFORE DELETE ON events
                BEGIN
                    SELECT RAISE(ABORT, 'events are append-only');
                END;
                """
            )

    def next_id(self, year: int, connection: sqlite3.Connection) -> str:
        connection.execute(
            """
            INSERT INTO decision_sequences(year, last_value) VALUES (?, 1)
            ON CONFLICT(year) DO UPDATE SET last_value = last_value + 1
            """,
            (year,),
        )
        value = connection.execute(
            "SELECT last_value FROM decision_sequences WHERE year = ?", (year,)
        ).fetchone()[0]
        return f"DR-{year}-{value:04d}"

    def append(
        self,
        connection: sqlite3.Connection,
        decision: Decision,
        event_type: str,
        occurred_at: datetime,
    ) -> Event:
        payload = decision.model_dump(mode="json", by_alias=True)
        payload_json = canonical_json(payload)
        previous = connection.execute(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        prev_hash = previous[0] if previous else None
        event_hash = hash_parts(
            prev_hash,
            decision.id,
            event_type,
            occurred_at.isoformat(),
            payload_json,
        )
        cursor = connection.execute(
            """
            INSERT INTO events(
                decision_id, event_type, occurred_at, payload_json,
                prev_event_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                decision.id,
                event_type,
                occurred_at.isoformat(),
                payload_json,
                prev_hash,
                event_hash,
            ),
        )
        connection.execute(
            """
            INSERT INTO decisions(decision_id, state_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(decision_id) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (decision.id, payload_json, occurred_at.isoformat()),
        )
        return Event(
            sequence=cursor.lastrowid,
            decision_id=decision.id,
            event_type=event_type,
            occurred_at=occurred_at,
            payload=payload,
            prev_event_hash=prev_hash,
            event_hash=event_hash,
        )

    def get(self, decision_id: str) -> Decision | None:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM decisions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
        return Decision.model_validate_json(row[0]) if row else None

    def list(self, statuses: list[str] | None = None) -> list[Decision]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT state_json FROM decisions ORDER BY decision_id"
            ).fetchall()
        decisions = [Decision.model_validate_json(row[0]) for row in rows]
        return [item for item in decisions if not statuses or item.status.value in statuses]

    def events(self, decision_id: str | None = None) -> list[Event]:
        self.initialize()
        query = "SELECT * FROM events"
        parameters: tuple[str, ...] = ()
        if decision_id:
            query += " WHERE decision_id = ?"
            parameters = (decision_id,)
        query += " ORDER BY sequence"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            Event(
                sequence=row["sequence"],
                decision_id=row["decision_id"],
                event_type=row["event_type"],
                occurred_at=row["occurred_at"],
                payload=json.loads(row["payload_json"]),
                prev_event_hash=row["prev_event_hash"],
                event_hash=row["event_hash"],
            )
            for row in rows
        ]

    def verify(self) -> tuple[bool, str]:
        """Verify the event chain and each committed snapshot chain."""
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
            expected_prev = None
            commit_head = None
            for row in rows:
                expected_event_hash = hash_parts(
                    expected_prev,
                    row["decision_id"],
                    row["event_type"],
                    row["occurred_at"],
                    row["payload_json"],
                )
                if row["prev_event_hash"] != expected_prev or row["event_hash"] != expected_event_hash:
                    return False, f"event chain failed at sequence {row['sequence']}"
                expected_prev = row["event_hash"]

                if row["event_type"] == "COMMITTED":
                    payload = json.loads(row["payload_json"])
                    integrity = payload["integrity"]
                    snapshot = dict(payload)
                    snapshot["integrity"] = {"commit_hash": None, "prev_hash": None, "amendments": []}
                    expected_commit = hash_parts(commit_head, canonical_json(snapshot))
                    if integrity["prev_hash"] != commit_head or integrity["commit_hash"] != expected_commit:
                        return False, f"commit chain failed for {row['decision_id']}"
                    commit_head = expected_commit

            stored_head = connection.execute(
                "SELECT head_hash FROM commit_chain WHERE singleton = 1"
            ).fetchone()[0]
            if stored_head != commit_head:
                return False, "stored commit-chain head does not match events"
        return True, "integrity verified"

