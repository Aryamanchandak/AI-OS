from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from gateway.platform.database import SQLiteDatabase

_SCHEMA = """CREATE TABLE IF NOT EXISTS calls (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
 provider TEXT NOT NULL, model TEXT NOT NULL,
 input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
 cache_create_tokens INTEGER DEFAULT 0, cache_read_tokens INTEGER DEFAULT 0,
 latency_ms INTEGER DEFAULT 0, status TEXT, error TEXT,
 prompt_chars INTEGER DEFAULT 0, response_chars INTEGER DEFAULT 0,
 override TEXT, attempted TEXT, tool_calls INTEGER DEFAULT 0,
 reasoning_applied INTEGER DEFAULT 0, tool_dialect TEXT,
 call_role TEXT DEFAULT 'worker', router_decision TEXT, embed_dim INTEGER,
 tenant TEXT, project TEXT, user TEXT, agent TEXT, session TEXT,
 retries INTEGER DEFAULT 0,
 usd REAL DEFAULT 0, price_source TEXT, cache_hit INTEGER DEFAULT 0,
 cache_kind TEXT, role TEXT, tier TEXT, escalations INTEGER DEFAULT 0,
 tokens_saved INTEGER DEFAULT 0, usd_saved REAL DEFAULT 0, profile TEXT);
CREATE INDEX IF NOT EXISTS idx_calls_ts ON calls(ts DESC);
CREATE INDEX IF NOT EXISTS idx_calls_provider_ts ON calls(provider, ts DESC);
CREATE INDEX IF NOT EXISTS idx_calls_agent_ts ON calls(agent, ts DESC);
CREATE INDEX IF NOT EXISTS idx_calls_session_ts ON calls(session, ts DESC);"""


class CallLedger:
    def __init__(self, path: Path) -> None:
        self.database = SQLiteDatabase(path)
        self.database.migrate([_SCHEMA])
        self._migrate_columns()

    def _migrate_columns(self) -> None:
        desired = {
            "cache_create_tokens": "INTEGER DEFAULT 0",
            "cache_read_tokens": "INTEGER DEFAULT 0",
            "prompt_chars": "INTEGER DEFAULT 0",
            "response_chars": "INTEGER DEFAULT 0",
            "override": "TEXT", "attempted": "TEXT", "tool_calls": "INTEGER DEFAULT 0",
            "reasoning_applied": "INTEGER DEFAULT 0", "tool_dialect": "TEXT",
            "call_role": "TEXT DEFAULT 'worker'", "router_decision": "TEXT",
            "embed_dim": "INTEGER", "tenant": "TEXT", "project": "TEXT", "user": "TEXT",
            "agent": "TEXT", "session": "TEXT", "retries": "INTEGER DEFAULT 0",
            "usd": "REAL DEFAULT 0", "price_source": "TEXT",
            "cache_hit": "INTEGER DEFAULT 0", "cache_kind": "TEXT", "role": "TEXT",
            "tier": "TEXT", "escalations": "INTEGER DEFAULT 0",
            "tokens_saved": "INTEGER DEFAULT 0", "usd_saved": "REAL DEFAULT 0",
            "profile": "TEXT",
        }
        with self.database.connect() as connection:
            present = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(calls)").fetchall()
            }
            for name, declaration in desired.items():
                if name not in present:
                    connection.execute(f'ALTER TABLE calls ADD COLUMN "{name}" {declaration}')

    def append(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        status: str = "ok",
        error: str | None = None,
        tenant: str | None = None,
        project: str | None = None,
        user: str | None = None,
        agent: str | None = None,
        session: str | None = None,
        usd: float = 0,
        price_source: str | None = None,
        cache_hit: bool = False,
        cache_kind: str | None = None,
        role: str | None = None,
        tier: str | None = None,
        profile: str | None = None,
    ) -> int:
        values = (
            time.time(), provider, model, input_tokens, output_tokens, latency_ms,
            status, error, tenant, project, user, agent, session, float(usd),
            price_source, int(cache_hit), cache_kind, role, tier, profile,
        )
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO calls
                (ts, provider, model, input_tokens, output_tokens, latency_ms, status, error,
                 tenant, project, user, agent, session, usd, price_source, cache_hit,
                 cache_kind, role, tier, profile)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            return int(cursor.lastrowid or 0)

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            return [
                dict(row)
                for row in connection.execute("SELECT * FROM calls ORDER BY ts DESC LIMIT ?", (limit,))
            ]

    def healthcheck(self) -> None:
        with self.database.connect() as connection:
            connection.execute("SELECT 1 FROM calls LIMIT 1").fetchone()
