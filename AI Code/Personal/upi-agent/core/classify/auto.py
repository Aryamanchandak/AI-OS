"""
Auto-categorization ensemble.

Each classifier is a function (payment, conn) -> list[Signal]. The ensemble
sums weights per category and picks the top one if total clears
CONFIDENCE_THRESHOLD.

Signals are returned even when they lose, so the reasoning trace can be
saved into the agent_event payload for later audit.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

from core import config
from core.classify.rules import upsert_rule
from core.utils.tokens import name_tokens


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    classifier: str
    category: str
    weight: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClassificationResult:
    category: str | None
    confidence: float
    signals: list[Signal]

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "signals": [s.to_dict() for s in self.signals],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calendar_titles(payment: sqlite3.Row) -> list[str]:
    """Extract event titles from the JSON calendar_events column."""
    raw = payment["calendar_events"] if "calendar_events" in payment.keys() else None
    if not raw:
        return []
    try:
        events = json.loads(raw)
        return [e.get("title", "") for e in events if e.get("title")]
    except (json.JSONDecodeError, TypeError):
        return []


def _haystack(payment: sqlite3.Row) -> str:
    """Combined lowercased counterparty text for substring matching."""
    parts = []
    if payment["counterparty_name"]:
        parts.append(payment["counterparty_name"])
    if payment["counterparty_vpa"]:
        parts.append(payment["counterparty_vpa"])
    return " ".join(parts).lower()


# ---------------------------------------------------------------------------
# Individual classifiers
# ---------------------------------------------------------------------------

def history_signals(payment: sqlite3.Row, conn: sqlite3.Connection) -> list[Signal]:
    """Look up category_rules by VPA and by name tokens."""
    sigs: list[Signal] = []

    vpa = payment["counterparty_vpa"]
    if vpa:
        rows = conn.execute(
            """
            SELECT category, hits FROM category_rules
            WHERE key_kind = 'vpa' AND key_value = ?
            ORDER BY hits DESC
            """,
            (vpa.lower(),),
        ).fetchall()
        if rows:
            top = rows[0]
            if top["hits"] >= config.HISTORY_VPA_MIN_HITS:
                sigs.append(Signal(
                    classifier="history",
                    category=top["category"],
                    weight=config.HISTORY_VPA_WEIGHT,
                    reason=f"VPA matched {top['hits']}× {top['category']}",
                ))
            else:
                sigs.append(Signal(
                    classifier="history",
                    category=top["category"],
                    weight=config.HISTORY_TOKEN_WEIGHT * 0.5,
                    reason=f"VPA seen {top['hits']}× as {top['category']}",
                ))

    for tok in name_tokens(payment["counterparty_name"]):
        rows = conn.execute(
            """
            SELECT category, SUM(hits) AS total_hits FROM category_rules
            WHERE key_kind = 'name_token' AND key_value = ?
            GROUP BY category ORDER BY total_hits DESC
            """,
            (tok,),
        ).fetchall()
        if rows:
            top = rows[0]
            sigs.append(Signal(
                classifier="history",
                category=top["category"],
                weight=config.HISTORY_TOKEN_WEIGHT,
                reason=f"name token '{tok}' → {top['category']} ({top['total_hits']}×)",
            ))

    return sigs


def calendar_signals(payment: sqlite3.Row, conn: sqlite3.Connection) -> list[Signal]:
    """Match calendar event titles against keyword groups."""
    titles = _calendar_titles(payment)
    if not titles:
        return []

    for title in titles:
        lower = title.lower()
        for pattern, category in config.CALENDAR_KEYWORDS:
            if re.search(pattern, lower):
                return [Signal(
                    classifier="calendar",
                    category=category,
                    weight=config.CALENDAR_WEIGHT,
                    reason=f"calendar event '{title}' → {category}",
                )]
    return []


def merchant_signals(payment: sqlite3.Row, conn: sqlite3.Connection) -> list[Signal]:
    """Hand-curated merchant patterns. First match wins, single signal."""
    hay = _haystack(payment)
    if not hay:
        return []
    for pattern, category in config.MERCHANT_PATTERNS:
        if pattern in hay:
            return [Signal(
                classifier="merchant",
                category=category,
                weight=config.MERCHANT_WEIGHT,
                reason=f"merchant pattern '{pattern}' → {category}",
            )]
    return []


def heuristic_signals(payment: sqlite3.Row, conn: sqlite3.Connection) -> list[Signal]:
    """
    Cheap tiebreakers based on amount + time-of-day + day-of-month.

    Intentionally weak (HEURISTIC_WEIGHT = 0.3) — only tips decisions when
    stronger classifiers are silent or split.
    """
    sigs: list[Signal] = []
    amount = payment["amount"] or 0
    occurred = datetime.fromisoformat(payment["occurred_at"])
    hour = occurred.hour
    day = occurred.day

    if (config.CLASSIFIER_MORNING_HOUR_START <= hour < config.CLASSIFIER_MORNING_HOUR_END
            and config.CLASSIFIER_SMALL_AMOUNT_MIN <= amount <= config.CLASSIFIER_SMALL_AMOUNT_MAX):
        sigs.append(Signal(
            classifier="heuristic",
            category="Food",
            weight=config.HEURISTIC_WEIGHT,
            reason=f"morning ({hour:02d}:00) + small amount (₹{amount:.0f})",
        ))

    if (day <= 5
            and amount >= config.CLASSIFIER_LARGE_AMOUNT_1
            and amount % config.CLASSIFIER_ROUND_AMOUNT_MOD == 0):
        if amount >= config.CLASSIFIER_LARGE_AMOUNT_2:
            sigs.append(Signal(
                classifier="heuristic",
                category="Rent",
                weight=config.HEURISTIC_WEIGHT,
                reason=f"month-start + round ₹{amount:.0f} → likely Rent",
            ))
        else:
            sigs.append(Signal(
                classifier="heuristic",
                category="Bills",
                weight=config.HEURISTIC_WEIGHT,
                reason=f"month-start + round ₹{amount:.0f} → likely Bills",
            ))

    return sigs


ALL_CLASSIFIERS = [
    history_signals,
    calendar_signals,
    merchant_signals,
    heuristic_signals,
]


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------

def classify(payment: sqlite3.Row, conn: sqlite3.Connection) -> ClassificationResult:
    """Run all classifiers, aggregate by category, pick winner if it clears threshold."""
    all_signals: list[Signal] = []
    for fn in ALL_CLASSIFIERS:
        try:
            all_signals.extend(fn(payment, conn))
        except Exception as e:
            all_signals.append(Signal(
                classifier=fn.__name__,
                category="Other",
                weight=0.0,
                reason=f"classifier error: {e}",
            ))

    if not all_signals:
        return ClassificationResult(category=None, confidence=0.0, signals=[])

    totals: dict[str, float] = {}
    for s in all_signals:
        totals[s.category] = totals.get(s.category, 0) + s.weight

    winner_cat, winner_weight = max(totals.items(), key=lambda kv: kv[1])

    if winner_weight < config.CONFIDENCE_THRESHOLD:
        return ClassificationResult(
            category=None, confidence=winner_weight, signals=all_signals,
        )

    return ClassificationResult(
        category=winner_cat, confidence=winner_weight, signals=all_signals,
    )


# ---------------------------------------------------------------------------
# Learning loop: record user corrections
# ---------------------------------------------------------------------------

def record_user_categorization(
    payment_id: int, category: str, conn: sqlite3.Connection
) -> None:
    """
    Called by the dashboard when a user sets a category.

    Upserts into category_rules (VPA + meaningful name tokens), increments hits,
    refreshes last_seen. Marks the payment's category_source = 'user' so the
    agent never overwrites it.
    """
    if category not in config.CATEGORIES:
        return

    row = conn.execute(
        "SELECT counterparty_vpa, counterparty_name FROM payments WHERE id = ?",
        (payment_id,),
    ).fetchone()
    if not row:
        return

    if row["counterparty_vpa"]:
        upsert_rule(conn, key_kind="vpa", key_value=row["counterparty_vpa"].lower(), category=category)
    for tok in name_tokens(row["counterparty_name"]):
        upsert_rule(conn, key_kind="name_token", key_value=tok, category=category)

    conn.execute(
        "UPDATE payments SET category = ?, category_source = 'user' WHERE id = ?",
        (category, payment_id),
    )
