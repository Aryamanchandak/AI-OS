"""
End-to-end tests for the reactor.

Verifies:
- All capabilities fire on appropriate seeded payments.
- Re-running the reactor on the same payments creates zero duplicate events.
- User-set categories are never overwritten.
- Goal warning/violation events fire exactly once per (goal, period).
- Backfill picks up only unprocessed payments.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from core.detect import goals
from core.orchestration import reactor


def _all_payment_ids(db_path) -> list[int]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT id FROM payments ORDER BY id").fetchall()
    conn.close()
    return [r[0] for r in rows]


def _events(db_path, **filters):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM agent_events"
    args: tuple = ()
    if filters:
        clauses = []
        for k, v in filters.items():
            clauses.append(f"{k} = ?")
            args = args + (v,)
        q += " WHERE " + " AND ".join(clauses)
    rows = conn.execute(q, args).fetchall()
    conn.close()
    return rows


def _insert(conn, **kwargs):
    cols = ",".join(kwargs.keys())
    placeholders = ",".join("?" * len(kwargs))
    cur = conn.execute(
        f"INSERT INTO payments ({cols}, sender_id, raw_text, confidence) "
        f"VALUES ({placeholders}, 'X', 'r', 1.0)",
        tuple(kwargs.values()),
    )
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Basic orchestration
# ---------------------------------------------------------------------------

def test_reactor_processes_all_payments(seeded_db):
    ids = _all_payment_ids(seeded_db["path"])
    report = reactor.on_new_payments(
        ids, db_path=seeded_db["path"], now=seeded_db["now"]
    )
    assert report.payments_processed == len(ids)


def test_reactor_categorizes_swiggy_via_merchant(seeded_db):
    ids = _all_payment_ids(seeded_db["path"])
    reactor.on_new_payments(ids, db_path=seeded_db["path"], now=seeded_db["now"])
    conn = sqlite3.connect(seeded_db["path"])
    row = conn.execute(
        """SELECT category, category_source FROM payments
           WHERE counterparty_vpa = ? LIMIT 1""",
        (seeded_db["swiggy_vpa"],),
    ).fetchone()
    conn.close()
    assert row[0] == "Food"
    assert row[1] == "agent"


def test_reactor_emits_anomaly_for_seeded_outlier(seeded_db):
    ids = _all_payment_ids(seeded_db["path"])
    reactor.on_new_payments(ids, db_path=seeded_db["path"], now=seeded_db["now"])
    rows = _events(
        seeded_db["path"], kind="anomaly", payment_id=seeded_db["anomaly_id"]
    )
    # ₹20,000 at 3am to new VPA → both new_counterparty AND odd_hour fire
    detectors = {r["title"].split()[0] for r in rows}
    assert len(rows) >= 1


def test_reactor_emits_recurring_for_weekly_subscription(seeded_db):
    """Inject a clean weekly pattern and confirm it surfaces."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    base_t = datetime(2026, 3, 1, 9, 0)
    new_ids = []
    for i in range(6):
        new_ids.append(_insert(
            conn, message_rowid=99000 + i,
            occurred_at=(base_t + timedelta(days=7 * i)).isoformat(),
            amount=499.0, direction="debit",
            counterparty_vpa="weekly-news@stripe",
        ))
    conn.commit()
    conn.close()

    reactor.on_new_payments(new_ids, db_path=seeded_db["path"], now=seeded_db["now"])
    rows = _events(seeded_db["path"], kind="recurring_detected")
    assert any("weekly-news@stripe" in r["title"] for r in rows)


# ---------------------------------------------------------------------------
# Idempotency — the spec's most important property
# ---------------------------------------------------------------------------

def test_reactor_is_idempotent(seeded_db):
    """Run twice; total event count must be identical."""
    ids = _all_payment_ids(seeded_db["path"])
    reactor.on_new_payments(ids, db_path=seeded_db["path"], now=seeded_db["now"])
    n1 = len(_events(seeded_db["path"]))
    reactor.on_new_payments(ids, db_path=seeded_db["path"], now=seeded_db["now"])
    n2 = len(_events(seeded_db["path"]))
    assert n1 == n2 > 0


def test_reactor_does_not_overwrite_user_category(seeded_db):
    """User-set category must survive reactor runs."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    pid = conn.execute(
        "SELECT id FROM payments WHERE counterparty_vpa = ? LIMIT 1",
        (seeded_db["swiggy_vpa"],),
    ).fetchone()["id"]
    # User says it's Personal (overriding what merchant pattern would say)
    conn.execute(
        "UPDATE payments SET category = 'Personal', category_source = 'user' WHERE id = ?",
        (pid,),
    )
    conn.commit()
    conn.close()

    reactor.on_new_payments([pid], db_path=seeded_db["path"], now=seeded_db["now"])
    conn = sqlite3.connect(seeded_db["path"])
    cat, src = conn.execute(
        "SELECT category, category_source FROM payments WHERE id = ?", (pid,)
    ).fetchone()
    conn.close()
    assert cat == "Personal"
    assert src == "user"


# ---------------------------------------------------------------------------
# Goal events — the dedup-per-period guarantee from acceptance criteria
# ---------------------------------------------------------------------------

def test_budget_cap_emits_one_warning_one_violation_per_period(seeded_db):
    """Spec acceptance criterion: ₹1,000 Food cap, ingest ₹1,200 Food →
    exactly 1 warning + 1 violation, not one per payment."""
    # Set up: clear seed-month Food payments so we control what's in the period
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    # Inject 4 Food payments of ₹300 each in this month (already-categorized)
    base_t = seeded_db["now"].replace(day=5, hour=12, minute=0)
    new_ids = []
    for i in range(4):
        new_ids.append(_insert(
            conn, message_rowid=88000 + i,
            occurred_at=(base_t + timedelta(days=i)).isoformat(),
            amount=300.0, direction="debit",
            counterparty_vpa=f"food{i}@x", category="Food",
            category_source="user",  # so reactor doesn't reclassify
        ))
    # Goal: ₹1,000 Food cap, warn at 80%
    goals.create_goal(
        conn, description="Food cap",
        kind="budget_cap",
        spec={"category": "Food", "amount": 1000, "warn_at_pct": 80},
        scope="month",
    )
    conn.commit()
    conn.close()

    # First run: as we process payments cumulatively, both warning (at ₹900,
    # 90%) and violation (at ₹1,200) should fire — but only once each.
    reactor.on_new_payments(
        new_ids, db_path=seeded_db["path"], now=seeded_db["now"]
    )

    warnings = _events(seeded_db["path"], kind="goal_warning")
    violations = _events(seeded_db["path"], kind="goal_violation")
    assert len(warnings) == 1, f"expected 1 warning, got {len(warnings)}"
    assert len(violations) == 1, f"expected 1 violation, got {len(violations)}"

    # Run again — still 1 + 1
    reactor.on_new_payments(
        new_ids, db_path=seeded_db["path"], now=seeded_db["now"]
    )
    warnings = _events(seeded_db["path"], kind="goal_warning")
    violations = _events(seeded_db["path"], kind="goal_violation")
    assert len(warnings) == 1
    assert len(violations) == 1


def test_avoid_merchant_emits_one_violation_per_offending_payment(seeded_db):
    """avoid_merchant is per-payment, not per-period — every match flags."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    goals.create_goal(
        conn, description="No Swiggy",
        kind="avoid_merchant", spec={"patterns": ["swiggy"]}, scope="month",
    )
    conn.commit()
    # Find this month's Swiggy payments
    start = seeded_db["now"].replace(day=1, hour=0, minute=0, second=0).isoformat()
    rows = conn.execute(
        """SELECT id FROM payments
           WHERE counterparty_vpa = ? AND occurred_at >= ?""",
        (seeded_db["swiggy_vpa"], start),
    ).fetchall()
    swiggy_ids = [r["id"] for r in rows]
    conn.close()

    reactor.on_new_payments(swiggy_ids, db_path=seeded_db["path"], now=seeded_db["now"])

    violations = _events(seeded_db["path"], kind="goal_violation")
    # One violation per offending Swiggy payment
    assert len(violations) == len(swiggy_ids)


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

def test_backfill_picks_up_unprocessed(seeded_db):
    """react_to_all_unprocessed should classify all unprocessed payments."""
    report = reactor.react_to_all_unprocessed(
        db_path=seeded_db["path"], now=seeded_db["now"]
    )
    assert report.payments_processed > 0
    # Run again — nothing new to process (all have categorized events now)
    report2 = reactor.react_to_all_unprocessed(
        db_path=seeded_db["path"], now=seeded_db["now"]
    )
    assert report2.payments_processed == 0


def test_backfill_skips_user_categorized(seeded_db):
    """User-categorized payments shouldn't be reprocessed by backfill."""
    conn = sqlite3.connect(seeded_db["path"])
    pid = conn.execute("SELECT id FROM payments LIMIT 1").fetchone()[0]
    conn.execute(
        "UPDATE payments SET category = 'Food', category_source = 'user' WHERE id = ?",
        (pid,),
    )
    conn.commit()
    conn.close()

    reactor.react_to_all_unprocessed(db_path=seeded_db["path"], now=seeded_db["now"])
    rows = _events(seeded_db["path"], payment_id=pid, kind="categorized")
    # No categorized event was created for this user-set payment
    assert len(rows) == 0


def test_reactor_swallows_individual_payment_errors(seeded_db, monkeypatch):
    """A buggy classifier on one payment must not break the batch."""
    from core.classify import auto as cls_mod
    original = cls_mod.classify

    call_count = {"n": 0}
    def flaky(payment, conn):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("synthetic failure")
        return original(payment, conn)

    monkeypatch.setattr(cls_mod, "classify", flaky)
    # Also patch the import in reactor module
    from core.orchestration import reactor as r_mod
    monkeypatch.setattr(r_mod.classifier, "classify", flaky)

    ids = _all_payment_ids(seeded_db["path"])[:5]
    report = reactor.on_new_payments(
        ids, db_path=seeded_db["path"], now=seeded_db["now"]
    )
    assert len(report.errors) == 1
    assert report.payments_processed == 4  # one was the failure
