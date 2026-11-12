"""
Goals / promises tracking.

Three kinds:
  - avoid_merchant: any payment matching the patterns is a violation.
  - budget_cap:     spend in a category capped at an amount per scope period.
  - frequency_cap:  no more than N payments to the patterns per scope period.

Scope: 'week' | 'month' | 'custom'. Week is ISO (Mon–Sun). Month is calendar.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from typing import Callable

from core import config
from core.utils.money import _money


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class GoalStatus:
    state: str                  # 'ok' | 'warning' | 'violated'
    progress: float             # 0–1+ for budgets; 0 or 1 for boolean kinds
    message: str
    offending_payment_ids: list[int]

    def to_dict(self) -> dict:
        return asdict(self)


NowFn = Callable[[], datetime]


def _default_now() -> datetime:
    return datetime.now()


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------

def period_bounds(scope: str, now: datetime) -> tuple[datetime, datetime]:
    """
    Return (start, end_exclusive) datetimes for the period containing `now`.

    - 'week': Monday 00:00:00 → next Monday 00:00:00 (ISO week).
    - 'month': 1st of month 00:00:00 → 1st of next month 00:00:00.
    - 'custom': returns (epoch, far_future) as a no-op.
    """
    if scope == "week":
        start_d = now.date() - timedelta(days=now.weekday())
        start = datetime.combine(start_d, datetime.min.time())
        end = start + timedelta(days=7)
    elif scope == "month":
        start = datetime(now.year, now.month, 1)
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1)
        else:
            end = datetime(now.year, now.month + 1, 1)
    else:
        start = datetime(1970, 1, 1)
        end = datetime(2999, 1, 1)
    return start, end


def period_label(scope: str, now: datetime) -> str:
    """Stable string label for a period — used in dedup keys."""
    if scope == "week":
        iso = now.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if scope == "month":
        return f"{now.year}-{now.month:02d}"
    return "custom"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_goal(
    conn: sqlite3.Connection, *,
    description: str, kind: str, spec: dict, scope: str,
    start_date: str | None = None, end_date: str | None = None,
) -> int:
    if kind not in ("avoid_merchant", "budget_cap", "frequency_cap"):
        raise ValueError(f"unknown goal kind: {kind}")
    if scope not in ("week", "month", "custom"):
        raise ValueError(f"unknown goal scope: {scope}")

    now = datetime.now()
    cur = conn.execute(
        """
        INSERT INTO goals (created_at, description, kind, spec_json, scope,
                           start_date, end_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        (now.isoformat(), description, kind, json.dumps(spec), scope,
         start_date or now.date().isoformat(), end_date),
    )
    return cur.lastrowid


def list_goals(conn: sqlite3.Connection, *, status: str | None = None) -> list[sqlite3.Row]:
    q = "SELECT * FROM goals"
    args: tuple = ()
    if status:
        q += " WHERE status = ?"
        args = (status,)
    q += " ORDER BY created_at DESC"
    return conn.execute(q, args).fetchall()


def set_status(conn: sqlite3.Connection, goal_id: int, status: str) -> None:
    if status not in ("active", "paused", "ended"):
        raise ValueError(f"invalid status: {status}")
    conn.execute("UPDATE goals SET status = ? WHERE id = ?", (status, goal_id))


def get_goal(conn: sqlite3.Connection, goal_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def match_pattern(payment: sqlite3.Row, pattern: str) -> bool:
    """Case-insensitive substring match against counterparty name OR VPA."""
    pat = pattern.lower()
    name = (payment["counterparty_name"] or "").lower()
    vpa = (payment["counterparty_vpa"] or "").lower()
    return pat in name or pat in vpa


# Keep private alias for backwards compat with any code that used the private name.
_matches_pattern = match_pattern


def _payments_in_scope(
    conn: sqlite3.Connection, scope: str, now: datetime,
    as_of_payment_id: int | None = None,
) -> list[sqlite3.Row]:
    """All debit payments occurring in the current scope period."""
    start, end = period_bounds(scope, now)
    if as_of_payment_id is not None:
        return conn.execute(
            """
            SELECT * FROM payments
            WHERE direction = 'debit'
              AND occurred_at >= ?
              AND occurred_at < ?
              AND id <= ?
            ORDER BY occurred_at ASC
            """,
            (start.isoformat(), end.isoformat(), as_of_payment_id),
        ).fetchall()
    return conn.execute(
        """
        SELECT * FROM payments
        WHERE direction = 'debit'
          AND occurred_at >= ?
          AND occurred_at < ?
        ORDER BY occurred_at ASC
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()


def evaluate(
    goal: sqlite3.Row, conn: sqlite3.Connection, *,
    now: NowFn | None = None,
    as_of_payment_id: int | None = None,
) -> GoalStatus:
    """Compute current state of a goal."""
    now_dt = (now or _default_now)()
    spec = json.loads(goal["spec_json"])
    payments = _payments_in_scope(conn, goal["scope"], now_dt, as_of_payment_id)

    if goal["kind"] == "avoid_merchant":
        patterns = [p.lower() for p in spec.get("patterns", [])]
        offending = [
            p for p in payments
            if any(match_pattern(p, pat) for pat in patterns)
        ]
        if offending:
            total = sum(p["amount"] or 0 for p in offending)
            return GoalStatus(
                state="violated", progress=1.0,
                message=(
                    f"{len(offending)} payment(s) matched ({_money(total)} total). "
                    f"Goal was to avoid: {', '.join(patterns)}."
                ),
                offending_payment_ids=[p["id"] for p in offending],
            )
        return GoalStatus(
            state="ok", progress=0.0,
            message=f"No payments matched patterns: {', '.join(patterns)}.",
            offending_payment_ids=[],
        )

    if goal["kind"] == "budget_cap":
        category = spec["category"]
        cap = float(spec["amount"])
        warn_pct = float(spec.get("warn_at_pct", config.DEFAULT_BUDGET_WARN_PCT))
        in_cat = [p for p in payments if (p["category"] or "") == category]
        spent = sum(p["amount"] or 0 for p in in_cat)
        progress = spent / cap if cap > 0 else 0.0

        if progress > 1.0:
            return GoalStatus(
                state="violated", progress=progress,
                message=(
                    f"{category} spend is {_money(spent)} of {_money(cap)} cap "
                    f"({progress*100:.0f}%) — over budget."
                ),
                offending_payment_ids=[p["id"] for p in in_cat],
            )
        if progress * 100 >= warn_pct:
            return GoalStatus(
                state="warning", progress=progress,
                message=(
                    f"{category} spend at {_money(spent)} of {_money(cap)} cap "
                    f"({progress*100:.0f}%). Approaching limit."
                ),
                offending_payment_ids=[p["id"] for p in in_cat],
            )
        return GoalStatus(
            state="ok", progress=progress,
            message=f"{category}: {_money(spent)} of {_money(cap)} ({progress*100:.0f}%).",
            offending_payment_ids=[p["id"] for p in in_cat],
        )

    if goal["kind"] == "frequency_cap":
        patterns = [p.lower() for p in spec.get("patterns", [])]
        max_n = int(spec["max_per_period"])
        matching = [
            p for p in payments
            if any(match_pattern(p, pat) for pat in patterns)
        ]
        progress = len(matching) / max_n if max_n > 0 else 0.0

        if len(matching) > max_n:
            return GoalStatus(
                state="violated", progress=progress,
                message=(
                    f"{len(matching)} payments to {', '.join(patterns)} "
                    f"this {goal['scope']}. Limit was {max_n}."
                ),
                offending_payment_ids=[p["id"] for p in matching],
            )
        if len(matching) == max_n:
            return GoalStatus(
                state="warning", progress=progress,
                message=(
                    f"At limit: {len(matching)}/{max_n} payments to "
                    f"{', '.join(patterns)} this {goal['scope']}."
                ),
                offending_payment_ids=[p["id"] for p in matching],
            )
        return GoalStatus(
            state="ok", progress=progress,
            message=(
                f"{len(matching)}/{max_n} payments to {', '.join(patterns)} "
                f"this {goal['scope']}."
            ),
            offending_payment_ids=[p["id"] for p in matching],
        )

    raise ValueError(f"unknown goal kind: {goal['kind']}")


# ---------------------------------------------------------------------------
# Cache management (used by daily cron + narrator)
# ---------------------------------------------------------------------------

def refresh_status_cache(conn: sqlite3.Connection, *, now: NowFn | None = None) -> None:
    """Recompute and store status for all active goals."""
    if conn.row_factory is not sqlite3.Row:
        conn.row_factory = sqlite3.Row
    now_dt = (now or _default_now)()
    for goal in list_goals(conn, status="active"):
        status = evaluate(goal, conn, now=lambda: now_dt)
        conn.execute(
            """
            INSERT INTO goal_status_cache (goal_id, state, progress, message, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(goal_id) DO UPDATE SET
              state = excluded.state,
              progress = excluded.progress,
              message = excluded.message,
              updated_at = excluded.updated_at
            """,
            (goal["id"], status.state, status.progress, status.message,
             now_dt.isoformat()),
        )
