"""
Shared test fixtures.

Builds a temp SQLite DB with the base `payments` table + brain tables,
seeded with ~60 synthetic payments across 6 weeks. Realistic mix:
- Recurring Swiggy debits (so HistoryClassifier has data once we record rules)
- A monthly rent
- Some calendar-tagged lunches
- One obvious anomaly: ₹20,000 at 3am to a new VPA
- Various small unknowns
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Make brain importable when pytest runs from project root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _base_payments_schema() -> str:
    """Extract the exact base SCHEMA so tests use real columns."""
    # agent.py lives alongside this conftest inside the brain package.
    src = (Path(__file__).resolve().parent.parent / "agent.py").read_text()
    m = re.search(r'SCHEMA = """(.*?)"""', src, re.DOTALL)
    assert m, "couldn't find SCHEMA in agent.py"
    return m.group(1)


def _insert_payment(
    conn: sqlite3.Connection,
    *,
    rowid: int,
    occurred_at: datetime,
    amount: float,
    direction: str = "debit",
    bank: str = "HDFC",
    vpa: str | None = None,
    name: str | None = None,
    calendar_event: str | None = None,
    confidence: float = 1.0,
) -> int:
    """Insert one payment and return its id."""
    cal = json.dumps([{"title": calendar_event, "start": "", "end": ""}]) if calendar_event else None
    cur = conn.execute(
        """
        INSERT INTO payments (
            message_rowid, occurred_at, amount, direction, bank,
            counterparty_vpa, counterparty_name,
            sender_id, raw_text, confidence, calendar_events
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (rowid, occurred_at.isoformat(), amount, direction, bank,
         vpa, name, "VM-TEST", "synthetic", confidence, cal),
    )
    return cur.lastrowid


@pytest.fixture
def now_local():
    """Pinned 'now' so week/month math is deterministic. A Wednesday."""
    return datetime(2026, 4, 22, 14, 0, 0)


@pytest.fixture
def seeded_db(tmp_path, now_local):
    """Temp DB with base + brain schema and ~60 synthetic payments."""
    db_path = tmp_path / "test.db"

    # Base schema first (so payments table exists before brain alters it).
    conn = sqlite3.connect(db_path)
    conn.executescript(_base_payments_schema())
    conn.commit()

    # Run brain migrations.
    from core.schema.db import reset_migration_cache
    reset_migration_cache()
    from core.schema.migrate import migrate as run_migrations
    run_migrations(db_path)

    # Reconnect for seeding (fresh state).
    conn = sqlite3.connect(db_path)

    rowid = 0
    # ---- 6 weeks of recurring Swiggy lunches: every 3-4 days, ~₹350 ----
    swiggy_vpa = "swiggy@axisbank"
    swiggy_dates = []
    for i in range(12):
        d = now_local - timedelta(days=42 - i * 3, hours=2)
        swiggy_dates.append(d)
        rowid += 1
        _insert_payment(
            conn, rowid=rowid, occurred_at=d, amount=320 + (i % 4) * 30,
            vpa=swiggy_vpa, name="SWIGGY",
        )

    # ---- Monthly rent: same VPA, same day each month, ₹25,000 ----
    for i in range(2):
        d = now_local.replace(day=2) - timedelta(days=30 * i)
        rowid += 1
        _insert_payment(
            conn, rowid=rowid, occurred_at=d, amount=25000.0,
            vpa="landlord@okhdfc", name="K SHARMA",
        )

    # ---- Calendar-tagged lunches: 5 of them, all to unknown VPAs ----
    for i, day_back in enumerate([3, 8, 15, 22, 30]):
        d = now_local - timedelta(days=day_back, hours=0, minutes=30)
        rowid += 1
        _insert_payment(
            conn, rowid=rowid,
            occurred_at=d.replace(hour=13, minute=20),
            amount=480.0 + i * 40,
            vpa=f"cafe{i}@paytm",
            name=None,
            calendar_event="Lunch with Aditi",
        )

    # ---- Uber rides: 4 over a month, irregular cadence ----
    for i, day_back in enumerate([2, 7, 14, 21]):
        d = now_local - timedelta(days=day_back, hours=5)
        rowid += 1
        _insert_payment(
            conn, rowid=rowid, occurred_at=d, amount=180.0 + i * 60,
            vpa="uber.payments@axisbank", name="UBER INDIA",
        )

    # ---- Groceries: weekly Blinkit ----
    for i in range(6):
        d = now_local - timedelta(days=42 - i * 7, hours=4)
        rowid += 1
        _insert_payment(
            conn, rowid=rowid, occurred_at=d, amount=850 + (i * 70),
            vpa="blinkit@ybl", name="BLINKIT",
        )

    # ---- Random small unknowns: chai, photocopy, parking ----
    unknowns = [
        (5, 25.0, "chai@paytm", None),
        (9, 60.0, "xerox@paytm", "PHOTOCOPY"),
        (12, 30.0, None, "PARKING ATTENDANT"),
        (18, 250.0, "vegetables@okaxis", None),
        (25, 110.0, None, "AUTO RICKSHAW"),
    ]
    for day_back, amt, vpa, name in unknowns:
        d = now_local - timedelta(days=day_back, hours=2)
        rowid += 1
        _insert_payment(
            conn, rowid=rowid, occurred_at=d, amount=amt, vpa=vpa, name=name,
        )

    # ---- THE ANOMALY: ₹20,000 at 3am to brand-new VPA, last week ----
    d = (now_local - timedelta(days=4)).replace(hour=3, minute=12)
    rowid += 1
    anomaly_id = _insert_payment(
        conn, rowid=rowid, occurred_at=d, amount=20000.0,
        vpa="suspicious@unknownbank", name="UNKNOWN PAYEE",
    )

    # ---- One credit (someone paid us back) ----
    rowid += 1
    _insert_payment(
        conn, rowid=rowid,
        occurred_at=now_local - timedelta(days=1),
        amount=2500.0, direction="credit",
        vpa="friend@oksbi", name="A KAPOOR",
    )

    conn.commit()

    # Sanity check
    n = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    assert n >= 30, f"seed produced only {n} payments"
    conn.close()

    return {
        "path": db_path,
        "now": now_local,
        "swiggy_vpa": swiggy_vpa,
        "swiggy_dates": swiggy_dates,
        "anomaly_id": anomaly_id,
    }
