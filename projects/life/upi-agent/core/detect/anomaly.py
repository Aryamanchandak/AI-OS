"""
Anomaly detection.

Four independent detectors. Each takes (payment, conn) and returns either an
AnomalyFinding (if it fires) or None. The reactor calls each one and emits
agent_events for findings.

Severity scale: 0 info, 1 notice, 2 warning, 3 critical.
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

from core import config
from core.utils.money import _money


@dataclass
class AnomalyFinding:
    detector: str            # 'new_counterparty' | 'zscore' | 'odd_hour' | 'velocity'
    severity: int            # 0..3
    title: str
    explanation: str
    payload: dict

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile. pct is 0–100."""
    if not values:
        raise ValueError("empty list")
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def detect_new_large_counterparty(
    payment: sqlite3.Row, conn: sqlite3.Connection
) -> AnomalyFinding | None:
    """First payment to a never-seen VPA above the threshold."""
    if payment["direction"] != "debit":
        return None
    amount = payment["amount"] or 0
    if amount <= config.NEW_COUNTERPARTY_THRESHOLD:
        return None
    vpa = payment["counterparty_vpa"]
    if not vpa:
        return None

    prior = conn.execute(
        """
        SELECT COUNT(*) FROM payments
        WHERE counterparty_vpa = ? AND id < ?
        """,
        (vpa, payment["id"]),
    ).fetchone()[0]
    if prior > 0:
        return None

    return AnomalyFinding(
        detector="new_counterparty",
        severity=2,
        title=f"First payment to {vpa} for {_money(amount)}",
        explanation=(
            f"This is your first transaction to {vpa}, and it's "
            f"{_money(amount)} — above the ₹{config.NEW_COUNTERPARTY_THRESHOLD:,} "
            f"threshold for new counterparties. Worth a glance to confirm it's "
            f"intentional."
        ),
        payload={"vpa": vpa, "amount": amount},
    )


def detect_amount_zscore(
    payment: sqlite3.Row, conn: sqlite3.Connection
) -> AnomalyFinding | None:
    """Payment is far above the mean for its category in the last N days."""
    if payment["direction"] != "debit":
        return None
    category = payment["category"]
    if not category:
        return None
    amount = payment["amount"] or 0
    if amount <= 0:
        return None

    cutoff = (datetime.fromisoformat(payment["occurred_at"])
              - timedelta(days=config.Z_LOOKBACK_DAYS)).isoformat()
    rows = conn.execute(
        """
        SELECT amount FROM payments
        WHERE direction = 'debit'
          AND category = ?
          AND occurred_at >= ?
          AND id < ?
        """,
        (category, cutoff, payment["id"]),
    ).fetchall()
    history = [r["amount"] for r in rows if r["amount"] is not None]
    if len(history) < config.Z_MIN_HISTORY:
        return None

    mu = statistics.mean(history)
    sigma = statistics.stdev(history) if len(history) >= 2 else 0
    if sigma == 0:
        return None

    z = (amount - mu) / sigma
    if z < config.Z_THRESHOLD:
        return None

    severity = 2 if z >= config.Z_HIGH_THRESHOLD else 1
    median = statistics.median(history)
    multiple = amount / median if median > 0 else float("inf")

    return AnomalyFinding(
        detector="zscore",
        severity=severity,
        title=f"Unusual {category} spend: {_money(amount)} ({multiple:.1f}× typical)",
        explanation=(
            f"{_money(amount)} is {z:.1f}σ above your typical {category} spend "
            f"over the last {config.Z_LOOKBACK_DAYS} days "
            f"(median {_money(median)}, mean {_money(mu)} ± {_money(sigma)})."
        ),
        payload={
            "category": category, "amount": amount, "z": round(z, 2),
            "median": median, "mean": mu, "stdev": sigma,
            "n_history": len(history),
        },
    )


def detect_odd_hour(
    payment: sqlite3.Row, conn: sqlite3.Connection
) -> AnomalyFinding | None:
    """Payment occurred outside the user's typical hour distribution."""
    if payment["direction"] != "debit":
        return None
    amount = payment["amount"] or 0
    if amount < config.ODD_HOUR_MIN_AMOUNT:
        return None

    hour = datetime.fromisoformat(payment["occurred_at"]).hour

    rows = conn.execute(
        """
        SELECT occurred_at FROM payments
        WHERE direction = 'debit' AND id < ?
        """,
        (payment["id"],),
    ).fetchall()
    if len(rows) < config.ODD_HOUR_MIN_HISTORY:
        return None

    hours = [datetime.fromisoformat(r["occurred_at"]).hour for r in rows]
    lo_pct, hi_pct = config.ODD_HOUR_PERCENTILES
    lo = _percentile(hours, lo_pct)
    hi = _percentile(hours, hi_pct)

    if lo <= hour <= hi:
        return None

    return AnomalyFinding(
        detector="odd_hour",
        severity=1,
        title=f"{_money(amount)} at {hour:02d}:xx — outside your usual hours",
        explanation=(
            f"This payment landed at {hour:02d}:xx. Your typical activity is "
            f"between {int(lo):02d}:00 and {int(hi):02d}:00 "
            f"(based on {len(hours)} prior debits). {_money(amount)} at this "
            f"hour is worth a check."
        ),
        payload={
            "hour": hour, "low_bound": lo, "high_bound": hi,
            "amount": amount, "n_history": len(hours),
        },
    )


def detect_velocity(
    payment: sqlite3.Row, conn: sqlite3.Connection
) -> AnomalyFinding | None:
    """N+ debits within W minutes — possible compromise."""
    if payment["direction"] != "debit":
        return None

    occurred = datetime.fromisoformat(payment["occurred_at"])
    window_start = (occurred - timedelta(minutes=config.VELOCITY_WINDOW_MIN)).isoformat()

    rows = conn.execute(
        """
        SELECT id, occurred_at, amount FROM payments
        WHERE direction = 'debit'
          AND occurred_at >= ?
          AND occurred_at <= ?
        ORDER BY occurred_at ASC
        """,
        (window_start, payment["occurred_at"]),
    ).fetchall()
    if len(rows) < config.VELOCITY_COUNT:
        return None

    first_id = rows[0]["id"]
    total = sum(r["amount"] or 0 for r in rows)

    return AnomalyFinding(
        detector="velocity",
        severity=3,
        title=f"{len(rows)} debits in {config.VELOCITY_WINDOW_MIN} min — possible compromise",
        explanation=(
            f"{len(rows)} debits totalling {_money(total)} happened in a "
            f"{config.VELOCITY_WINDOW_MIN}-minute window ending at "
            f"{occurred.strftime('%H:%M')}. This rate is unusual and may "
            f"indicate a compromised account or stuck retry loop."
        ),
        payload={
            "first_payment_id": first_id,
            "count": len(rows),
            "total": total,
            "window_minutes": config.VELOCITY_WINDOW_MIN,
        },
    )


ALL_DETECTORS = [
    detect_new_large_counterparty,
    detect_amount_zscore,
    detect_odd_hour,
    detect_velocity,
]


def run_all(payment: sqlite3.Row, conn: sqlite3.Connection) -> list[AnomalyFinding]:
    """Run every detector against a payment, return all findings."""
    findings: list[AnomalyFinding] = []
    for fn in ALL_DETECTORS:
        try:
            f = fn(payment, conn)
            if f:
                findings.append(f)
        except Exception:
            continue
    return findings


def dedup_key_for(payment_id: int, finding: AnomalyFinding) -> str:
    """Deterministic dedup key per (detector, payment) — except velocity,
    which dedupes per cluster."""
    if finding.detector == "velocity":
        first = finding.payload.get("first_payment_id", payment_id)
        return f"anomaly:velocity:first={first}"
    return f"anomaly:{finding.detector}:payment={payment_id}"
