"""SQLite-backed out-of-band identity pairing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable
import os

from gateway.platform.database import SQLiteDatabase

CODE_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class PairingRecord:
    channel: str
    channel_user_id: str
    user_handle: str
    trust_level: str
    paired_at: float


class PairingStore:
    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time) -> None:
        self.database = SQLiteDatabase(path)
        self._clock = clock
        self._lock = threading.Lock()
        self.initialize()

    def initialize(self) -> None:
        self.database.migrate(
            [
                """CREATE TABLE IF NOT EXISTS pairings (
                    channel TEXT NOT NULL, channel_user_id TEXT NOT NULL,
                    user_handle TEXT, trust_level TEXT NOT NULL, paired_at REAL NOT NULL,
                    PRIMARY KEY (channel, channel_user_id));
                   CREATE TABLE IF NOT EXISTS pending_codes (
                    code TEXT PRIMARY KEY, channel TEXT NOT NULL,
                    channel_user_id TEXT NOT NULL, user_handle TEXT,
                    requested_trust_level TEXT NOT NULL, expires_at REAL NOT NULL);"""
            ],
            autocommit=True,
        )

    def issue_code(
        self,
        channel: str,
        channel_user_id: str,
        user_handle: str = "",
        *,
        requested_trust_level: str = "user_paired",
    ) -> tuple[str, float]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = self._clock() + CODE_TTL_SECONDS
        with self._lock, self.database.connect(autocommit=True) as connection:
            connection.execute(
                """INSERT OR REPLACE INTO pending_codes
                   (code, channel, channel_user_id, user_handle, requested_trust_level, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (code, channel, channel_user_id, user_handle, requested_trust_level, expires_at),
            )
        return code, expires_at

    def confirm_code(self, code: str) -> PairingRecord | None:
        with self._lock, self.database.connect(autocommit=True) as connection:
            row = connection.execute("SELECT * FROM pending_codes WHERE code=?", (code,)).fetchone()
            if row is None:
                return None
            if float(row["expires_at"]) < self._clock():
                connection.execute("DELETE FROM pending_codes WHERE code=?", (code,))
                return None
            paired_at = self._clock()
            connection.execute(
                """INSERT OR REPLACE INTO pairings
                   (channel, channel_user_id, user_handle, trust_level, paired_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    row["channel"], row["channel_user_id"], row["user_handle"],
                    row["requested_trust_level"], paired_at,
                ),
            )
            connection.execute("DELETE FROM pending_codes WHERE code=?", (code,))
            return PairingRecord(
                str(row["channel"]), str(row["channel_user_id"]), str(row["user_handle"] or ""),
                str(row["requested_trust_level"]), paired_at,
            )

    def lookup(self, channel: str, channel_user_id: str) -> PairingRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM pairings WHERE channel=? AND channel_user_id=?",
                (channel, channel_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def all_pairings(self) -> list[PairingRecord]:
        with self.database.connect() as connection:
            return [self._record(row) for row in connection.execute("SELECT * FROM pairings")]

    def owners(self, channel: str | None = None) -> list[PairingRecord]:
        query = "SELECT * FROM pairings WHERE trust_level='owner_paired'"
        arguments: tuple[str, ...] = ()
        if channel is not None:
            query += " AND channel=?"
            arguments = (channel,)
        with self.database.connect() as connection:
            return [self._record(row) for row in connection.execute(query, arguments)]

    def revoke(self, channel: str, channel_user_id: str) -> bool:
        with self._lock, self.database.connect(autocommit=True) as connection:
            cursor = connection.execute(
                "DELETE FROM pairings WHERE channel=? AND channel_user_id=?",
                (channel, channel_user_id),
            )
            return cursor.rowcount > 0

    def force_pair_owner(
        self, channel: str, channel_user_id: str, user_handle: str = "owner"
    ) -> PairingRecord:
        paired_at = self._clock()
        with self.database.connect(autocommit=True) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO pairings VALUES (?, ?, ?, 'owner_paired', ?)",
                (channel, channel_user_id, user_handle, paired_at),
            )
        return PairingRecord(channel, channel_user_id, user_handle, "owner_paired", paired_at)

    @staticmethod
    def _record(row: sqlite3.Row) -> PairingRecord:
        return PairingRecord(
            str(row["channel"]), str(row["channel_user_id"]), str(row["user_handle"] or ""),
            str(row["trust_level"]), float(row["paired_at"]),
        )

    def healthcheck(self) -> None:
        with self.database.connect() as connection:
            connection.execute("SELECT 1 FROM pairings LIMIT 1").fetchone()


# Provider adapters are deliberately kept vertically self-contained and retain
# their historic zero-argument pairing lookup. Gateway binds the lifespan-owned
# store here before any adapter is activated. The fallback exists for adapter
# tests and standalone setup tools only.
_singleton: PairingStore | None = None


def bind_pairing_store(store: PairingStore | None) -> None:
    global _singleton
    _singleton = store


def get_pairing_store() -> PairingStore:
    global _singleton
    if _singleton is None:
        from gateway.platform.configuration import GLCPaths

        _singleton = PairingStore(GLCPaths(os.environ).pairing_db)
    return _singleton
