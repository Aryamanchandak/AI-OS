"""Tests for brain.goals."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from core.detect import goals


def _insert(conn, **kwargs):
    cols = ",".join(kwargs.keys())
    placeholders = ",".join("?" * len(kwargs))
    cur = conn.execute(
        f"INSERT INTO payments ({cols}, sender_id, raw_text, confidence) "
        f"VALUES ({placeholders}, 'X', 'r', 1.0)",
        tuple(kwargs.values()),
    )
    return cur.lastrowid


# --- Period bounds -----------------------------------------------------------

def test_week_bounds_iso():
    """2026-04-22 is a Wednesday; ISO week starts Mon 2026-04-20."""
    now = datetime(2026, 4, 22, 14, 0)
    start, end = goals.period_bounds("week", now)
    assert start == datetime(2026, 4, 20)
    assert end == datetime(2026, 4, 27)


def test_month_bounds():
    now = datetime(2026, 4, 22, 14, 0)
    start, end = goals.period_bounds("month", now)
    assert start == datetime(2026, 4, 1)
    assert end == datetime(2026, 5, 1)


def test_month_bounds_year_rollover():
    now = datetime(2026, 12, 15)
    start, end = goals.period_bounds("month", now)
    assert start == datetime(2026, 12, 1)
    assert end == datetime(2027, 1, 1)


def test_period_label():
    now = datetime(2026, 4, 22)
    assert goals.period_label("week", now) == "2026-W17"
    assert goals.period_label("month", now) == "2026-04"


# --- avoid_merchant ----------------------------------------------------------

def test_avoid_merchant_violated_when_match(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    gid = goals.create_goal(
        conn, description="No Swiggy", kind="avoid_merchant",
        spec={"patterns": ["swiggy"]}, scope="month",
    )
    conn.commit()
    goal = goals.get_goal(conn, gid)
    # Seed has Swiggy payments in current month
    status = goals.evaluate(goal, conn, now=lambda: seeded_db["now"])
    assert status.state == "violated"
    assert len(status.offending_payment_ids) > 0


def test_avoid_merchant_ok_when_no_match(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    gid = goals.create_goal(
        conn, description="Avoid uniques", kind="avoid_merchant",
        spec={"patterns": ["nonexistent_merchant_xyz"]}, scope="month",
    )
    conn.commit()
    goal = goals.get_goal(conn, gid)
    status = goals.evaluate(goal, conn, now=lambda: seeded_db["now"])
    assert status.state == "ok"


# --- budget_cap --------------------------------------------------------------

def test_budget_cap_state_transitions(seeded_db):
    """Cross 80% → warning, cross 100% → violated."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    # Inject Food payments precisely
    base_t = seeded_db["now"].replace(day=5, hour=12, minute=0)
    for i in range(3):
        _insert(
            conn, message_rowid=10000 + i,
            occurred_at=(base_t + timedelta(days=i)).isoformat(),
            amount=300.0, direction="debit",
            counterparty_vpa=f"food{i}@x", category="Food",
        )
    conn.commit()
    gid = goals.create_goal(
        conn, description="Food cap", kind="budget_cap",
        spec={"category": "Food", "amount": 1000, "warn_at_pct": 80},
        scope="month",
    )
    conn.commit()
    goal = goals.get_goal(conn, gid)

    # 900 spent → 90% → warning
    status = goals.evaluate(goal, conn, now=lambda: seeded_db["now"])
    assert status.state == "warning"
    assert 0.85 <= status.progress <= 0.95

    # Push to 1200 → over → violated
    _insert(
        conn, message_rowid=10999,
        occurred_at=base_t.isoformat(),
        amount=300.0, direction="debit",
        counterparty_vpa="food3@x", category="Food",
    )
    conn.commit()
    status = goals.evaluate(goal, conn, now=lambda: seeded_db["now"])
    assert status.state == "violated"
    assert status.progress > 1.0


def test_budget_cap_ok_under_warning_threshold(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    base_t = seeded_db["now"].replace(day=5)
    _insert(
        conn, message_rowid=20001,
        occurred_at=base_t.isoformat(),
        amount=200.0, direction="debit",
        counterparty_vpa="x@x", category="Food",
    )
    conn.commit()
    gid = goals.create_goal(
        conn, description="Food cap", kind="budget_cap",
        spec={"category": "Food", "amount": 1000, "warn_at_pct": 80},
        scope="month",
    )
    conn.commit()
    goal = goals.get_goal(conn, gid)
    status = goals.evaluate(goal, conn, now=lambda: seeded_db["now"])
    assert status.state == "ok"


def test_budget_cap_only_counts_current_period(seeded_db):
    """Payments from prior month must not count toward current month's cap."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    # Payment 50 days back (definitely prior month)
    old = seeded_db["now"] - timedelta(days=50)
    _insert(
        conn, message_rowid=30001,
        occurred_at=old.isoformat(),
        amount=99999.0, direction="debit",
        counterparty_vpa="ancient@x", category="Food",
    )
    conn.commit()
    gid = goals.create_goal(
        conn, description="Food cap", kind="budget_cap",
        spec={"category": "Food", "amount": 1000, "warn_at_pct": 80},
        scope="month",
    )
    conn.commit()
    goal = goals.get_goal(conn, gid)
    status = goals.evaluate(goal, conn, now=lambda: seeded_db["now"])
    assert status.state == "ok"


# --- frequency_cap -----------------------------------------------------------

def test_frequency_cap_at_limit_warns(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    base_t = seeded_db["now"].replace(hour=12, minute=0)  # this week
    monday = base_t - timedelta(days=base_t.weekday())
    for i in range(2):
        _insert(
            conn, message_rowid=40000 + i,
            occurred_at=(monday + timedelta(days=i)).isoformat(),
            amount=400.0, direction="debit",
            counterparty_name="ZOMATO ORDER",
        )
    conn.commit()
    gid = goals.create_goal(
        conn, description="Max 2 Zomato", kind="frequency_cap",
        spec={"patterns": ["zomato"], "max_per_period": 2},
        scope="week",
    )
    conn.commit()
    goal = goals.get_goal(conn, gid)
    status = goals.evaluate(goal, conn, now=lambda: seeded_db["now"])
    assert status.state == "warning"


def test_frequency_cap_violated_over_limit(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    monday = seeded_db["now"] - timedelta(days=seeded_db["now"].weekday())
    for i in range(3):
        _insert(
            conn, message_rowid=50000 + i,
            occurred_at=(monday + timedelta(days=i, hours=12)).isoformat(),
            amount=400.0, direction="debit",
            counterparty_name="ZOMATO ORDER",
        )
    conn.commit()
    gid = goals.create_goal(
        conn, description="Max 2 Zomato", kind="frequency_cap",
        spec={"patterns": ["zomato"], "max_per_period": 2},
        scope="week",
    )
    conn.commit()
    goal = goals.get_goal(conn, gid)
    status = goals.evaluate(goal, conn, now=lambda: seeded_db["now"])
    assert status.state == "violated"


# --- Status cache + lifecycle -----------------------------------------------

def test_refresh_status_cache_writes_rows(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    goals.create_goal(
        conn, description="No Swiggy", kind="avoid_merchant",
        spec={"patterns": ["swiggy"]}, scope="month",
    )
    conn.commit()
    goals.refresh_status_cache(conn, now=lambda: seeded_db["now"])
    conn.commit()
    rows = conn.execute("SELECT * FROM goal_status_cache").fetchall()
    assert len(rows) == 1
    assert rows[0]["state"] == "violated"


def test_set_status_lifecycle(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    gid = goals.create_goal(
        conn, description="x", kind="avoid_merchant",
        spec={"patterns": ["x"]}, scope="month",
    )
    goals.set_status(conn, gid, "paused")
    assert goals.get_goal(conn, gid)["status"] == "paused"
    goals.set_status(conn, gid, "ended")
    assert goals.get_goal(conn, gid)["status"] == "ended"
    with pytest.raises(ValueError):
        goals.set_status(conn, gid, "bogus")


def test_create_goal_rejects_invalid_kind(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    with pytest.raises(ValueError):
        goals.create_goal(
            conn, description="x", kind="bogus_kind",
            spec={}, scope="week",
        )
