"""Tests for brain.classifier."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from core.classify import auto as classifier
from core import config


def _payment(conn: sqlite3.Connection, payment_id: int) -> sqlite3.Row:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()


def test_merchant_classifier_recognizes_swiggy(seeded_db):
    """Swiggy VPA should hit the merchant classifier without history."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    p = conn.execute(
        "SELECT * FROM payments WHERE counterparty_vpa = ? LIMIT 1",
        (seeded_db["swiggy_vpa"],),
    ).fetchone()
    result = classifier.classify(p, conn)
    assert result.category == "Food"
    assert result.confidence >= config.MERCHANT_WEIGHT


def test_calendar_classifier_lunch_event(seeded_db):
    """A 'Lunch with Aditi' event on a payment with no merchant pattern → Food."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    p = conn.execute(
        "SELECT * FROM payments WHERE counterparty_vpa LIKE 'cafe%@paytm' LIMIT 1"
    ).fetchone()
    result = classifier.classify(p, conn)
    assert result.category == "Food"
    # Confidence comes from CALENDAR_WEIGHT alone (and maybe heuristic).
    cal_signals = [s for s in result.signals if s.classifier == "calendar"]
    assert len(cal_signals) == 1
    assert "Lunch with Aditi" in cal_signals[0].reason


def test_history_beats_merchant_when_user_has_corrected(seeded_db):
    """Once the user records 'tea@ybl' as Personal, future payments to it
    should classify as Personal — even though it has no merchant pattern."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row

    # Insert a payment first
    cur = conn.execute(
        """INSERT INTO payments
           (message_rowid, occurred_at, amount, direction,
            counterparty_vpa, sender_id, raw_text, confidence)
           VALUES (9001, ?, 60, 'debit', 'tea@ybl', 'X', 'r', 1.0)""",
        (datetime(2026, 4, 22, 11, 0).isoformat(),),
    )
    pid = cur.lastrowid
    conn.commit()

    # User corrects it 4 times (different payments to same VPA)
    for _ in range(4):
        classifier.record_user_categorization(pid, "Personal", conn)
    conn.commit()

    p = _payment(conn, pid)
    result = classifier.classify(p, conn)
    assert result.category == "Personal"
    # Should be highest-weight signal
    history_signals = [s for s in result.signals if s.classifier == "history"]
    assert any("VPA matched" in s.reason for s in history_signals)


def test_below_threshold_returns_none(seeded_db):
    """A payment with no signals should be uncategorized."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    # Random unknown — vegetables@okaxis is in seed data with no patterns
    p = conn.execute(
        "SELECT * FROM payments WHERE counterparty_vpa = 'vegetables@okaxis' LIMIT 1"
    ).fetchone()
    result = classifier.classify(p, conn)
    # No merchant pattern, no calendar, no history yet → None
    # (Heuristic alone — 0.3 — won't clear the 0.6 threshold)
    assert result.category is None
    assert result.confidence < config.CONFIDENCE_THRESHOLD


def test_heuristic_alone_does_not_classify(seeded_db):
    """Heuristic at 0.3 must not single-handedly cross the 0.6 threshold."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    # Morning chai — only heuristic should fire
    cur = conn.execute(
        """INSERT INTO payments
           (message_rowid, occurred_at, amount, direction,
            counterparty_vpa, sender_id, raw_text, confidence)
           VALUES (9999, ?, 80, 'debit', 'random@paytm', 'X', 'r', 1.0)""",
        (datetime(2026, 4, 22, 8, 30).isoformat(),),
    )
    pid = cur.lastrowid
    conn.commit()
    p = _payment(conn, pid)
    result = classifier.classify(p, conn)
    # Heuristic would say Food, but at 0.3 alone it can't cross 0.6.
    assert result.category is None


def test_ensemble_combines_signals(seeded_db):
    """Calendar (0.6) + heuristic (0.3) for 'Lunch with Aditi' at 13:20 → 0.9.
    But the heuristic 'morning + small' won't fire at 13:20 — so this tests
    that the strong single signal is enough."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    p = conn.execute(
        "SELECT * FROM payments WHERE counterparty_vpa LIKE 'cafe%@paytm' LIMIT 1"
    ).fetchone()
    result = classifier.classify(p, conn)
    assert result.category == "Food"


def test_record_user_categorization_creates_rules(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    p = conn.execute("SELECT id FROM payments LIMIT 1").fetchone()

    classifier.record_user_categorization(p["id"], "Food", conn)
    rules = conn.execute("SELECT * FROM category_rules").fetchall()
    assert len(rules) >= 1
    # Marks user-source on payment
    src = conn.execute(
        "SELECT category_source FROM payments WHERE id = ?", (p["id"],)
    ).fetchone()[0]
    assert src == "user"


def test_record_user_categorization_increments_hits(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    p = conn.execute(
        "SELECT id FROM payments WHERE counterparty_vpa = ? LIMIT 1",
        (seeded_db["swiggy_vpa"],),
    ).fetchone()
    for _ in range(3):
        classifier.record_user_categorization(p["id"], "Food", conn)
    row = conn.execute(
        "SELECT hits FROM category_rules WHERE key_kind='vpa' AND key_value=?",
        (seeded_db["swiggy_vpa"],),
    ).fetchone()
    assert row["hits"] == 3


def test_record_unknown_category_is_rejected(seeded_db):
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    p = conn.execute("SELECT id FROM payments LIMIT 1").fetchone()
    classifier.record_user_categorization(p["id"], "BogusCategory", conn)
    # No rule should be created
    n = conn.execute("SELECT COUNT(*) FROM category_rules").fetchone()[0]
    assert n == 0
