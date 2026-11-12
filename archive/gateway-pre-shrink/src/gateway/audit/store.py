"""Domain-owned append-only audit database with fail-closed writes."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from gateway.platform.database import SQLiteDatabase

_SCHEMA = """CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, session_id TEXT,
 channel TEXT NOT NULL, channel_user_id TEXT NOT NULL, trust_level TEXT NOT NULL,
 event_type TEXT NOT NULL, tool TEXT, policy_verdict TEXT, params_json TEXT, result_json TEXT);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_channel ON audit_log(channel, ts DESC);
CREATE TABLE IF NOT EXISTS audit_schema (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);
INSERT OR IGNORE INTO audit_schema VALUES (1, strftime('%s','now'));"""


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value, default=str)


class AuditStore:
    """Every append is autocommitted; write failures propagate (fail-closed)."""

    failure_policy = "closed"

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)
        self.database.migrate([_SCHEMA], autocommit=True)

    def append(
        self,
        *,
        channel: str,
        channel_user_id: str,
        trust_level: str,
        event_type: str,
        session_id: str | None = None,
        tool: str | None = None,
        policy_verdict: str | None = None,
        params: Any = None,
        result: Any = None,
    ) -> int:
        with self.database.connect(autocommit=True) as connection:
            cursor = connection.execute(
                """INSERT INTO audit_log
                (ts, session_id, channel, channel_user_id, trust_level, event_type,
                 tool, policy_verdict, params_json, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (time.time(), session_id, channel, channel_user_id, trust_level,
                 event_type, tool, policy_verdict, _json(params), _json(result)),
            )
            return int(cursor.lastrowid or 0)

    def query(
        self, *, limit: int = 100, session_id: str | None = None, channel: str | None = None
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        arguments: list[object] = []
        if session_id:
            clauses.append("session_id=?")
            arguments.append(session_id)
        if channel:
            clauses.append("channel=?")
            arguments.append(channel)
        query = "SELECT * FROM audit_log"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY ts DESC LIMIT ?"
        arguments.append(limit)
        with self.database.connect() as connection:
            return [dict(row) for row in connection.execute(query, arguments)]

    def healthcheck(self) -> None:
        with self.database.connect() as connection:
            version = connection.execute("SELECT MAX(version) FROM audit_schema").fetchone()
            if version is None or version[0] != 1:
                raise RuntimeError("unsupported audit schema")
