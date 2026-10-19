from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from gateway.platform.database import SQLiteDatabase

# The one column list: the table, migrations and inserts are all built from it.
COLUMNS = {
    "kind": "TEXT NOT NULL DEFAULT 'chat'",
    "provider": "TEXT NOT NULL", "model": "TEXT NOT NULL",
    "input_tokens": "INTEGER DEFAULT 0", "output_tokens": "INTEGER DEFAULT 0",
    "cache_read_tokens": "INTEGER DEFAULT 0", "cache_create_tokens": "INTEGER DEFAULT 0",
    "usd": "REAL DEFAULT 0", "price_source": "TEXT",
    "latency_ms": "INTEGER DEFAULT 0", "status": "TEXT", "error": "TEXT",
    "attempted": "TEXT", "retries": "INTEGER DEFAULT 0",
    "agent": "TEXT", "session": "TEXT", "profile": "TEXT",
}

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, "
    + ", ".join(f"{name} {declaration}" for name, declaration in COLUMNS.items()) + ");"
)
_INDEXES = """CREATE INDEX IF NOT EXISTS idx_calls_ts ON calls(ts DESC);
CREATE INDEX IF NOT EXISTS idx_calls_agent_ts ON calls(agent, ts DESC);
CREATE INDEX IF NOT EXISTS idx_calls_session_ts ON calls(session, ts DESC);"""


class CallLedger:
    """Append-only record of every LLM call; write failures propagate (fail-closed)."""

    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)
        self.database.migrate([_SCHEMA])
        self._add_missing_columns()
        self.database.migrate([_INDEXES])

    def _add_missing_columns(self) -> None:
        # Older databases keep their unused columns; only missing ones are added.
        with self.database.connect() as connection:
            present = {str(row["name"]) for row in connection.execute("PRAGMA table_info(calls)")}
            for name, declaration in COLUMNS.items():
                if name not in present:
                    connection.execute(f"ALTER TABLE calls ADD COLUMN {name} {declaration.replace(' NOT NULL', '')}")

    def append(self, **row: Any) -> int:
        unknown = set(row) - COLUMNS.keys()
        if unknown:
            raise ValueError(f"unknown ledger columns: {sorted(unknown)}")
        if "attempted" in row:
            row["attempted"] = json.dumps(row["attempted"], default=str)
        names = ["ts", *row]
        with self.database.connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO calls ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})",
                (time.time(), *row.values()),
            )
            return int(cursor.lastrowid or 0)

    def recent(self, limit: int = 100, provider: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        query = f"SELECT id, ts, {', '.join(COLUMNS)} FROM calls WHERE (? IS NULL OR provider = ?) AND (? IS NULL OR status = ?) ORDER BY ts DESC, id DESC LIMIT ?"
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(query, (provider, provider, status, status, limit))]
        for row in rows:
            row["attempted"] = json.loads(row["attempted"]) if row["attempted"] else []
        return rows

    def rollup(self, dimension: str, *, value: str | None = None, session: str | None = None,
               since: float = 0, group_by_provider: bool = True) -> list[dict[str, Any]]:
        if dimension not in COLUMNS:
            raise ValueError(f"unknown column {dimension!r}")
        provider = "provider" if group_by_provider else "'*'"
        query = (f"SELECT {dimension} AS value, {provider} AS provider, COUNT(*) AS calls, COALESCE(SUM(usd), 0) AS dollars "
                 f"FROM calls WHERE {dimension} IS NOT NULL AND ts >= ? AND (? IS NULL OR {dimension} = ?) "
                 f"AND (? IS NULL OR session = ?) GROUP BY 1, 2 ORDER BY 1, 2")
        with self.database.connect() as connection:
            rows = connection.execute(query, (since, value, value, session, session))
            return [{"dimension": dimension, **dict(row)} for row in rows]

    def by_provider(self, *, since: float = 0) -> dict[str, dict[str, Any]]:
        query = ("SELECT provider, COUNT(*) AS calls, COALESCE(SUM(input_tokens), 0) AS input_tokens, "
                 "COALESCE(SUM(output_tokens), 0) AS output_tokens, COALESCE(SUM(usd), 0) AS dollars "
                 "FROM calls WHERE ts >= ? GROUP BY provider")
        with self.database.connect() as connection:
            return {row["provider"]: {key: row[key] for key in ("calls", "input_tokens", "output_tokens", "dollars")}
                    for row in connection.execute(query, (since,))}

    def healthcheck(self) -> None:
        with self.database.connect() as connection:
            connection.execute("SELECT 1 FROM calls LIMIT 1").fetchone()
