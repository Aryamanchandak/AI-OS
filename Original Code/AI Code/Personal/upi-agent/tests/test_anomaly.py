"""Tests for brain.anomaly and brain.recurring."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from core.detect import anomaly, recurring
from core import config


def _row(conn, payment_id):
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()


def _insert(conn, **kwargs):
    cols = ",".join(kwargs.keys())
    placeholders = ",".join("?" * len(kwargs))
    cur = conn.execute(
        f"INSERT INTO payments ({cols}, sender_id, raw_text, confidence) "
        f"VALUES ({placeholders}, 'X', 'r', 1.0)",
        tuple(kwargs.values()),
    )
    return cur.lastrowid


# --- NewLargeCounterparty ----------------------------------------------------

def test_new_large_counterparty_fires(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    p = _row(conn, seeded_db["anomaly_id"])
    f = anomaly.detect_new_large_counterparty(p, conn)
    assert f is not None
    assert f.severity == 2
    assert "suspicious@unknownbank" in f.title


def test_new_large_counterparty_does_not_fire_for_known_vpa(seeded_db):
    """Second swiggy payment shouldn't fire — VPA is known."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    pid = _insert(
        conn,
        message_rowid=99001,
        occurred_at=datetime(2026, 4, 22, 13, 0).isoformat(),
        amount=4500.0, direction="debit",
        counterparty_vpa=seeded_db["swiggy_vpa"],
    )
    conn.commit()
    p = _row(conn, pid)
    assert anomaly.detect_new_large_counterparty(p, conn) is None


def test_new_large_counterparty_does_not_fire_below_threshold(seeded_db):
    """₹500 to a new VPA isn't large enough."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    pid = _insert(
        conn,
        message_rowid=99002,
        occurred_at=datetime(2026, 4, 22, 13, 0).isoformat(),
        amount=500.0, direction="debit",
        counterparty_vpa="newperson@oksbi",
    )
    conn.commit()
    p = _row(conn, pid)
    assert anomaly.detect_new_large_counterparty(p, conn) is None


# --- AmountZScore ------------------------------------------------------------

def test_zscore_fires_on_huge_food_charge(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    # First, populate Food category history (≥ Z_MIN_HISTORY entries).
    base_t = datetime(2026, 3, 1, 13, 0)
    for i in range(15):
        _insert(
            conn,
            message_rowid=10000 + i,
            occurred_at=(base_t + timedelta(days=i)).isoformat(),
            amount=300.0 + (i % 4) * 50,  # ~300–450
            direction="debit",
            counterparty_vpa=f"food{i}@paytm",
            category="Food",
        )
    # Now an outlier: ₹3,000 in Food category
    pid = _insert(
        conn,
        message_rowid=20000,
        occurred_at=datetime(2026, 4, 22, 13, 0).isoformat(),
        amount=3000.0, direction="debit",
        counterparty_vpa="bigmeal@paytm",
        category="Food",
    )
    conn.commit()
    p = _row(conn, pid)
    f = anomaly.detect_amount_zscore(p, conn)
    assert f is not None
    assert f.severity >= 1
    assert "Food" in f.title


def test_zscore_does_not_fire_with_insufficient_history(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    # Only 5 prior Food entries — below Z_MIN_HISTORY (10).
    base_t = datetime(2026, 3, 1)
    for i in range(5):
        _insert(
            conn, message_rowid=30000 + i,
            occurred_at=(base_t + timedelta(days=i)).isoformat(),
            amount=300.0, direction="debit",
            counterparty_vpa=f"x{i}@paytm",
            category="Food",
        )
    pid = _insert(
        conn, message_rowid=40000,
        occurred_at=datetime(2026, 4, 22).isoformat(),
        amount=5000.0, direction="debit",
        counterparty_vpa="big@paytm",
        category="Food",
    )
    conn.commit()
    p = _row(conn, pid)
    assert anomaly.detect_amount_zscore(p, conn) is None


def test_zscore_skips_uncategorized(seeded_db):
    """Without a category we can't compute a baseline."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    pid = _insert(
        conn, message_rowid=50000,
        occurred_at=datetime(2026, 4, 22).isoformat(),
        amount=99999.0, direction="debit",
        counterparty_vpa="huge@paytm",  # category left null
    )
    conn.commit()
    p = _row(conn, pid)
    assert anomaly.detect_amount_zscore(p, conn) is None


# --- OddHour -----------------------------------------------------------------

def test_odd_hour_fires_at_3am(seeded_db):
    """The seeded ₹20,000 at 3am anomaly should fire on this detector too
    (since seed has 30+ debits during normal hours)."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    p = _row(conn, seeded_db["anomaly_id"])
    f = anomaly.detect_odd_hour(p, conn)
    assert f is not None
    assert f.severity == 1


def test_odd_hour_does_not_fire_during_business_hours(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    pid = _insert(
        conn, message_rowid=60000,
        occurred_at=datetime(2026, 4, 22, 12, 0).isoformat(),
        amount=2000.0, direction="debit",
        counterparty_vpa="lunch@paytm",
    )
    conn.commit()
    p = _row(conn, pid)
    # 12:00 is solidly within the seeded distribution (9–13)
    assert anomaly.detect_odd_hour(p, conn) is None


# --- Velocity ----------------------------------------------------------------

def test_velocity_fires_on_burst(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    burst_start = datetime(2026, 4, 22, 15, 0)
    last_id = None
    for i in range(5):
        last_id = _insert(
            conn, message_rowid=70000 + i,
            occurred_at=(burst_start + timedelta(minutes=i * 2)).isoformat(),
            amount=500.0, direction="debit",
            counterparty_vpa=f"burst{i}@paytm",
        )
    conn.commit()
    p = _row(conn, last_id)
    f = anomaly.detect_velocity(p, conn)
    assert f is not None
    assert f.severity == 3
    assert f.payload["count"] == 5


def test_velocity_does_not_fire_on_spread_out_payments(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    base_t = datetime(2026, 4, 22, 10, 0)
    last_id = None
    for i in range(5):
        last_id = _insert(
            conn, message_rowid=80000 + i,
            occurred_at=(base_t + timedelta(hours=i)).isoformat(),
            amount=500.0, direction="debit",
            counterparty_vpa=f"slow{i}@paytm",
        )
    conn.commit()
    p = _row(conn, last_id)
    assert anomaly.detect_velocity(p, conn) is None


def test_velocity_dedup_key_uses_first_payment(seeded_db):
    """Dedup key for velocity must be the same regardless of which payment
    in the cluster triggered detection."""
    f = anomaly.AnomalyFinding(
        detector="velocity", severity=3,
        title="x", explanation="x",
        payload={"first_payment_id": 42, "count": 5, "total": 1000, "window_minutes": 10},
    )
    key = anomaly.dedup_key_for(99, f)
    assert "first=42" in key


# --- Recurring detector ------------------------------------------------------

def test_recurring_finds_swiggy_cadence(seeded_db):
    """Seed has 12 Swiggy payments every 3 days — that's not a known cadence,
    but let's verify the detector handles it correctly (no false positive)."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    clusters = recurring.find_recurring(conn)
    # 3-day cadence isn't in our list (weekly/fortnightly/monthly), so
    # Swiggy shouldn't be classified as recurring.
    swiggy = [c for c in clusters if c.counterparty == seeded_db["swiggy_vpa"]]
    assert not swiggy


def test_recurring_finds_weekly_blinkit(seeded_db):
    """Blinkit is 7-day cadence in seed → should be detected as weekly."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    clusters = recurring.find_recurring(conn)
    blinkit = [c for c in clusters if "blinkit" in c.counterparty]
    # Amounts are 850, 920, 990, 1060, 1130, 1200 — that's 41% spread,
    # over the 10% RECURRING_AMOUNT_TOLERANCE → should NOT be detected.
    # This guards against the detector being too permissive.
    assert not blinkit, "amounts vary too much; should not classify as recurring"


def test_recurring_classifies_consistent_weekly(seeded_db):
    """Inject a clean weekly subscription with stable amount → should detect."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    base_t = datetime(2026, 3, 1, 9, 0)
    for i in range(6):
        _insert(
            conn, message_rowid=90000 + i,
            occurred_at=(base_t + timedelta(days=7 * i)).isoformat(),
            amount=499.0, direction="debit",
            counterparty_vpa="weekly-news@stripe",
            counterparty_name="WEEKLY NEWS SUB",
        )
    conn.commit()
    clusters = recurring.find_recurring(conn)
    target = [c for c in clusters if c.counterparty == "weekly-news@stripe"]
    assert len(target) == 1
    assert target[0].cadence == "weekly"
    assert target[0].occurrences == 6


def test_recurring_classifies_monthly_rent(seeded_db):
    """Inject 4 consecutive monthly payments with consistent 30-day gaps."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    base_t = datetime(2026, 1, 2, 9, 0)
    for i in range(4):
        _insert(
            conn, message_rowid=91000 + i,
            occurred_at=(base_t + timedelta(days=30 * i)).isoformat(),
            amount=18000.0, direction="debit",
            counterparty_vpa="rent-detector-test@okhdfc",
            counterparty_name="LANDLORD TEST",
        )
    conn.commit()
    clusters = recurring.find_recurring(conn)
    rent = [c for c in clusters if c.counterparty == "rent-detector-test@okhdfc"]
    assert len(rent) == 1
    assert rent[0].cadence == "monthly"
    assert rent[0].occurrences == 4


def test_refresh_recurring_is_idempotent(seeded_db):
    """Running refresh twice should leave only one row per cluster."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    base_t = datetime(2026, 3, 1, 9, 0)
    for i in range(6):
        _insert(
            conn, message_rowid=92000 + i,
            occurred_at=(base_t + timedelta(days=7 * i)).isoformat(),
            amount=499.0, direction="debit",
            counterparty_vpa="weekly-x@stripe",
        )
    conn.commit()
    recurring.refresh_recurring(conn)
    recurring.refresh_recurring(conn)
    n = conn.execute(
        "SELECT COUNT(*) FROM recurring_payments WHERE counterparty='weekly-x@stripe'"
    ).fetchone()[0]
    assert n == 1
