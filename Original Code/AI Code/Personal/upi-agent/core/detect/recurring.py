"""
Recurring payment detector.

Mines history for clusters of payments to the same counterparty at regular
intervals. Detects weekly (7d), fortnightly (14d), and monthly (28–31d)
cadences. Writes one row per cluster to recurring_payments and emits
agent_events for newly-detected ones.

Run periodically (daily-ish), not per-payment. The reactor calls
`refresh_recurring(conn)` after each ingestion batch.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from core import config


@dataclass
class RecurringCluster:
    counterparty: str
    counterparty_kind: str    # 'vpa' | 'name'
    cadence: str              # 'weekly' | 'fortnightly' | 'monthly'
    typical_amount: float
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    next_expected: datetime
    payment_ids: list[int]


def _classify_cadence(median_gap_days: float) -> str | None:
    """Map a median gap (in days) to a named cadence, or None if it doesn't fit."""
    tol = config.RECURRING_CADENCE_TOLERANCE
    candidates = [("weekly", 7), ("fortnightly", 14), ("monthly", 30)]
    for name, target in candidates:
        if abs(median_gap_days - target) <= tol:
            return name
    return None


def _amounts_consistent(amounts: list[float]) -> bool:
    """All amounts within the configured fraction of the median."""
    if not amounts:
        return False
    med = statistics.median(amounts)
    if med <= 0:
        return False
    tol = config.RECURRING_AMOUNT_TOLERANCE
    return all(abs(a - med) / med <= tol for a in amounts)


def find_recurring(conn: sqlite3.Connection) -> list[RecurringCluster]:
    """Scan all debits, cluster by counterparty, return recurring clusters."""
    rows = conn.execute(
        """
        SELECT id, occurred_at, amount, counterparty_vpa, counterparty_name
        FROM payments
        WHERE direction = 'debit' AND amount IS NOT NULL
        ORDER BY occurred_at ASC
        """
    ).fetchall()

    groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        if r["counterparty_vpa"]:
            key = ("vpa", r["counterparty_vpa"].lower())
        elif r["counterparty_name"]:
            key = ("name", r["counterparty_name"].lower().strip())
        else:
            continue
        groups[key].append(r)

    clusters: list[RecurringCluster] = []

    for (kind, counterparty), members in groups.items():
        if len(members) < config.RECURRING_MIN_OCCURRENCES:
            continue

        dates = [datetime.fromisoformat(r["occurred_at"]) for r in members]
        amounts = [r["amount"] for r in members]

        if not _amounts_consistent(amounts):
            continue

        gaps = [(dates[i+1] - dates[i]).total_seconds() / 86400
                for i in range(len(dates) - 1)]
        if not gaps:
            continue
        median_gap = statistics.median(gaps)

        cadence = _classify_cadence(median_gap)
        if not cadence:
            continue

        target_gap = {"weekly": 7, "fortnightly": 14, "monthly": 30}[cadence]
        consistent = sum(
            1 for g in gaps if abs(g - target_gap) <= config.RECURRING_CADENCE_TOLERANCE
        )
        if consistent < len(gaps) * 0.7:
            continue

        last_seen = dates[-1]
        next_expected = last_seen + timedelta(days=target_gap)

        clusters.append(RecurringCluster(
            counterparty=counterparty,
            counterparty_kind=kind,
            cadence=cadence,
            typical_amount=statistics.median(amounts),
            occurrences=len(members),
            first_seen=dates[0],
            last_seen=last_seen,
            next_expected=next_expected,
            payment_ids=[r["id"] for r in members],
        ))

    return clusters


def refresh_recurring(conn: sqlite3.Connection) -> list[RecurringCluster]:
    """
    Detect clusters and upsert into recurring_payments.

    Returns the full list. The caller (reactor) compares against existing
    rows to emit `recurring_detected` events only for new clusters.
    """
    clusters = find_recurring(conn)
    for c in clusters:
        conn.execute(
            """
            INSERT INTO recurring_payments
              (counterparty, counterparty_kind, cadence, typical_amount,
               occurrences, first_seen, last_seen, next_expected, payment_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(counterparty, counterparty_kind, cadence) DO UPDATE SET
              typical_amount = excluded.typical_amount,
              occurrences    = excluded.occurrences,
              last_seen      = excluded.last_seen,
              next_expected  = excluded.next_expected,
              payment_ids    = excluded.payment_ids
            """,
            (
                c.counterparty, c.counterparty_kind, c.cadence,
                c.typical_amount, c.occurrences,
                c.first_seen.isoformat(), c.last_seen.isoformat(),
                c.next_expected.isoformat(),
                json.dumps(c.payment_ids),
            ),
        )
    return clusters


def previously_known(conn: sqlite3.Connection) -> set[tuple[str, str, str]]:
    """Return set of (counterparty, kind, cadence) keys already in the table."""
    rows = conn.execute(
        "SELECT counterparty, counterparty_kind, cadence FROM recurring_payments"
    ).fetchall()
    return {(r[0], r[1], r[2]) for r in rows}
