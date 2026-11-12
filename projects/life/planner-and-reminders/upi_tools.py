"""
UPI tool helpers for the chat agent.

Read-only queries against the UPI ledger (~/.upi-agent/data.db). Each
helper returns a JSON-friendly dict (or list); on missing DB / read errors
it returns a structured error dict so the agent can render a useful reply
instead of crashing.

Imported by `planner.py` and surfaced as agent tools (see TOOL_SCHEMAS).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

# Match brain.config.DB_PATH without importing the brain package — keeps
# this module independent so a missing brain install doesn't break tools.
DB_PATH = Path.home() / ".upi-agent" / "data.db"

_NO_DATA_MESSAGE = (
    "No UPI data yet. Run the daily check (or `python -m brain.agent`) once "
    "the iPhone→Mac SMS forwarding + Full Disk Access are set up."
)


@contextmanager
def _open_db() -> Iterator[sqlite3.Connection | None]:
    if not DB_PATH.exists():
        yield None
        return
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _err(msg: str) -> dict:
    return {"ok": False, "message": msg}


# --- Queries -----------------------------------------------------------------

def spend_today() -> dict:
    """Total debited today (local date)."""
    today = datetime.now().date().isoformat()
    with _open_db() as conn:
        if conn is None:
            return _err(_NO_DATA_MESSAGE)
        try:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total,
                       COUNT(*) AS txns
                FROM payments
                WHERE direction = 'debit'
                  AND substr(occurred_at, 1, 10) = ?
                """,
                (today,),
            ).fetchone()
        except sqlite3.Error as e:
            return _err(f"DB read failed: {e}")
    return {
        "ok": True,
        "date": today,
        "total_inr": float(row["total"] or 0),
        "transactions": int(row["txns"] or 0),
    }


def spend_by_category(category: str | None = None, days: int = 30) -> dict:
    """
    Spend totals grouped by category over the last `days` days.
    If `category` is given, return only that category's total.
    """
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with _open_db() as conn:
        if conn is None:
            return _err(_NO_DATA_MESSAGE)
        try:
            if category:
                row = conn.execute(
                    """
                    SELECT COALESCE(SUM(amount), 0) AS total,
                           COUNT(*) AS txns
                    FROM payments
                    WHERE direction = 'debit'
                      AND occurred_at >= ?
                      AND LOWER(category) = LOWER(?)
                    """,
                    (since, category),
                ).fetchone()
                return {
                    "ok": True,
                    "category": category,
                    "window_days": days,
                    "total_inr": float(row["total"] or 0),
                    "transactions": int(row["txns"] or 0),
                }
            rows = conn.execute(
                """
                SELECT COALESCE(category, 'Uncategorized') AS category,
                       SUM(amount) AS total,
                       COUNT(*) AS txns
                FROM payments
                WHERE direction = 'debit' AND occurred_at >= ?
                GROUP BY COALESCE(category, 'Uncategorized')
                ORDER BY total DESC
                """,
                (since,),
            ).fetchall()
        except sqlite3.Error as e:
            return _err(f"DB read failed: {e}")
    return {
        "ok": True,
        "window_days": days,
        "categories": [
            {
                "category": r["category"],
                "total_inr": float(r["total"] or 0),
                "transactions": int(r["txns"] or 0),
            }
            for r in rows
        ],
    }


def recent_payments(n: int = 10) -> dict:
    """Most recent payments, newest first."""
    n = max(1, min(int(n), 100))
    with _open_db() as conn:
        if conn is None:
            return _err(_NO_DATA_MESSAGE)
        try:
            rows = conn.execute(
                """
                SELECT id, occurred_at, amount, direction, bank,
                       counterparty_vpa, counterparty_name, category,
                       calendar_events
                FROM payments
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                (n,),
            ).fetchall()
        except sqlite3.Error as e:
            return _err(f"DB read failed: {e}")
    out = []
    for r in rows:
        d = dict(r)
        if d.get("calendar_events"):
            try:
                d["calendar_events"] = json.loads(d["calendar_events"])
            except (json.JSONDecodeError, TypeError):
                d["calendar_events"] = []
        else:
            d["calendar_events"] = []
        out.append(d)
    return {"ok": True, "count": len(out), "payments": out}


def top_recipients(days: int = 30, limit: int = 10) -> dict:
    """Top counterparties by total debit amount in the window."""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with _open_db() as conn:
        if conn is None:
            return _err(_NO_DATA_MESSAGE)
        try:
            rows = conn.execute(
                """
                SELECT COALESCE(counterparty_vpa, counterparty_name, '?') AS who,
                       COUNT(*) AS txns,
                       SUM(amount) AS total
                FROM payments
                WHERE direction = 'debit' AND occurred_at >= ?
                GROUP BY who
                ORDER BY total DESC
                LIMIT ?
                """,
                (since, limit),
            ).fetchall()
        except sqlite3.Error as e:
            return _err(f"DB read failed: {e}")
    return {
        "ok": True,
        "window_days": days,
        "recipients": [
            {
                "who": r["who"],
                "transactions": int(r["txns"] or 0),
                "total_inr": float(r["total"] or 0),
            }
            for r in rows
        ],
    }


def goals_status() -> dict:
    """Active goals and their current state (from goal_status_cache)."""
    with _open_db() as conn:
        if conn is None:
            return _err(_NO_DATA_MESSAGE)
        try:
            # Brain may not have run yet; the goals + goal_status_cache tables
            # only exist after a migration. Detect and return a friendly empty.
            tbls = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            if "goals" not in tbls:
                return {"ok": True, "goals": [], "note": "Brain layer not yet initialized."}
            rows = conn.execute(
                """
                SELECT g.id, g.description, g.kind, g.scope, g.status,
                       c.state, c.progress, c.message, c.updated_at
                FROM goals g
                LEFT JOIN goal_status_cache c ON c.goal_id = g.id
                WHERE g.status = 'active'
                ORDER BY g.created_at DESC
                """
            ).fetchall()
        except sqlite3.Error as e:
            return _err(f"DB read failed: {e}")
    return {
        "ok": True,
        "goals": [dict(r) for r in rows],
    }
