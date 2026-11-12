"""
Shared category_rules writer. Both the auto classifier (brain) and the manual
classifier (tax) call this to keep the table in sync via one canonical upsert.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime


def upsert_rule(
    conn: sqlite3.Connection,
    *,
    key_kind: str,
    key_value: str,
    category: str,
) -> None:
    """
    Upsert one rule into category_rules. Increments hits; refreshes last_seen.
    Does NOT commit — caller is responsible for the transaction boundary.
    """
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO category_rules (key_kind, key_value, category, hits, last_seen)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(key_kind, key_value, category)
        DO UPDATE SET hits = hits + 1, last_seen = excluded.last_seen
        """,
        (key_kind, key_value, category, now),
    )
