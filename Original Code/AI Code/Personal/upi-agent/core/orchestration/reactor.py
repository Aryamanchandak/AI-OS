"""
The reactor: orchestrates core modules in response to new payments.

Single public entry: `on_new_payments(payment_ids)` runs each through
classifier, anomaly detectors, and active goals. Emits agent_events
idempotently — repeat invocations create zero duplicates.

Dedup is enforced at the SQL level via the UNIQUE dedup_key column +
INSERT OR IGNORE.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from core import config
from core.classify import auto as classifier
from core.detect import anomaly, goals, recurring
from core.schema.db import connect


log = logging.getLogger("core.orchestration.reactor")


@dataclass
class ReactorReport:
    payments_processed: int = 0
    categorized: int = 0
    anomalies_emitted: int = 0
    goal_events_emitted: int = 0
    recurring_detected: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"reactor: {self.payments_processed} payments, "
            f"{self.categorized} categorized, "
            f"{self.anomalies_emitted} anomalies, "
            f"{self.goal_events_emitted} goal events, "
            f"{self.recurring_detected} new recurring"
        )


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------

def _emit_event(
    conn: sqlite3.Connection, *,
    kind: str, title: str, explanation: str, dedup_key: str,
    severity: int = 0, payment_id: int | None = None, payload: dict | None = None,
) -> bool:
    """Insert an event idempotently. Returns True if a new row was created."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO agent_events
          (created_at, kind, payment_id, severity, title, explanation,
           payload_json, dedup_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            kind, payment_id, severity, title, explanation,
            json.dumps(payload) if payload is not None else None,
            dedup_key,
        ),
    )
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Per-payment processing
# ---------------------------------------------------------------------------

def _process_classifier(
    payment: sqlite3.Row, conn: sqlite3.Connection, report: ReactorReport
) -> None:
    if payment["category_source"] == "user":
        return

    result = classifier.classify(payment, conn)
    payload = result.to_dict()

    if result.category is None:
        _emit_event(
            conn,
            kind="categorized",
            payment_id=payment["id"],
            severity=0,
            title=f"Uncategorized — confidence {result.confidence:.2f}",
            explanation=(
                f"Classifier ran on payment #{payment['id']} but no category "
                f"cleared the {config.CONFIDENCE_THRESHOLD} threshold. "
                f"Highest signal weight: {result.confidence:.2f}."
            ),
            payload=payload,
            dedup_key=f"categorized:payment={payment['id']}",
        )
        return

    conn.execute(
        "UPDATE payments SET category = ?, category_source = 'agent' WHERE id = ?",
        (result.category, payment["id"]),
    )
    if _emit_event(
        conn,
        kind="categorized",
        payment_id=payment["id"],
        severity=0,
        title=f"Categorized as {result.category}",
        explanation=(
            f"Classified payment #{payment['id']} as {result.category} "
            f"with confidence {result.confidence:.2f}. "
            f"Top reason: {result.signals[0].reason if result.signals else 'n/a'}."
        ),
        payload=payload,
        dedup_key=f"categorized:payment={payment['id']}",
    ):
        report.categorized += 1


def _process_anomalies(
    payment: sqlite3.Row, conn: sqlite3.Connection, report: ReactorReport
) -> None:
    findings = anomaly.run_all(payment, conn)
    for f in findings:
        if _emit_event(
            conn,
            kind="anomaly",
            payment_id=payment["id"],
            severity=f.severity,
            title=f.title,
            explanation=f.explanation,
            payload={"detector": f.detector, **f.payload},
            dedup_key=anomaly.dedup_key_for(payment["id"], f),
        ):
            report.anomalies_emitted += 1


def _process_goals(
    payment: sqlite3.Row, conn: sqlite3.Connection, report: ReactorReport,
    *, now: datetime,
) -> None:
    active = goals.list_goals(conn, status="active")
    if not active:
        return

    for goal in active:
        spec = json.loads(goal["spec_json"])
        period = goals.period_label(goal["scope"], now)

        if goal["kind"] == "avoid_merchant":
            patterns = [p.lower() for p in spec.get("patterns", [])]
            if any(goals.match_pattern(payment, pat) for pat in patterns):
                if _emit_event(
                    conn,
                    kind="goal_violation",
                    payment_id=payment["id"],
                    severity=2,
                    title=f"Goal '{goal['description']}' violated",
                    explanation=(
                        f"Payment to "
                        f"{payment['counterparty_vpa'] or payment['counterparty_name']}"
                        f" matches a pattern you said you'd avoid: "
                        f"{', '.join(patterns)}."
                    ),
                    payload={"goal_id": goal["id"], "period": period},
                    dedup_key=f"goal_violation:goal={goal['id']}:payment={payment['id']}",
                ):
                    report.goal_events_emitted += 1

        elif goal["kind"] == "budget_cap":
            status = goals.evaluate(
                goal, conn, now=lambda: now,
                as_of_payment_id=payment["id"],
            )
            if status.state == "warning":
                if _emit_event(
                    conn,
                    kind="goal_warning",
                    payment_id=payment["id"],
                    severity=2,
                    title=f"Approaching budget: {goal['description']}",
                    explanation=status.message,
                    payload={"goal_id": goal["id"], "period": period,
                             "progress": status.progress},
                    dedup_key=f"goal_warning:goal={goal['id']}:period={period}",
                ):
                    report.goal_events_emitted += 1
            elif status.state == "violated":
                if _emit_event(
                    conn,
                    kind="goal_violation",
                    payment_id=payment["id"],
                    severity=3,
                    title=f"Budget exceeded: {goal['description']}",
                    explanation=status.message,
                    payload={"goal_id": goal["id"], "period": period,
                             "progress": status.progress},
                    dedup_key=f"goal_violation:goal={goal['id']}:period={period}",
                ):
                    report.goal_events_emitted += 1

        elif goal["kind"] == "frequency_cap":
            status = goals.evaluate(
                goal, conn, now=lambda: now,
                as_of_payment_id=payment["id"],
            )
            if status.state == "warning":
                if _emit_event(
                    conn,
                    kind="goal_warning",
                    payment_id=payment["id"],
                    severity=1,
                    title=f"At limit: {goal['description']}",
                    explanation=status.message,
                    payload={"goal_id": goal["id"], "period": period,
                             "progress": status.progress},
                    dedup_key=f"goal_warning:goal={goal['id']}:period={period}",
                ):
                    report.goal_events_emitted += 1
            elif status.state == "violated":
                if _emit_event(
                    conn,
                    kind="goal_violation",
                    payment_id=payment["id"],
                    severity=2,
                    title=f"Frequency cap exceeded: {goal['description']}",
                    explanation=status.message,
                    payload={"goal_id": goal["id"], "period": period,
                             "progress": status.progress},
                    dedup_key=f"goal_violation:goal={goal['id']}:period={period}",
                ):
                    report.goal_events_emitted += 1


def _process_recurring(
    conn: sqlite3.Connection, report: ReactorReport
) -> None:
    """Detect recurring clusters; emit events for newly-discovered ones."""
    known = recurring.previously_known(conn)
    clusters = recurring.refresh_recurring(conn)
    for c in clusters:
        key = (c.counterparty, c.counterparty_kind, c.cadence)
        if key in known:
            continue
        if _emit_event(
            conn,
            kind="recurring_detected",
            severity=1,
            title=(
                f"Recurring {c.cadence} payment detected: "
                f"{c.counterparty} (~₹{int(c.typical_amount):,})"
            ),
            explanation=(
                f"Detected a {c.cadence} pattern of payments to "
                f"{c.counterparty}, around ₹{int(c.typical_amount):,} each, "
                f"observed {c.occurrences}× since "
                f"{c.first_seen.date().isoformat()}. "
                f"Next charge expected ~{c.next_expected.date().isoformat()}."
            ),
            payload={
                "counterparty": c.counterparty,
                "cadence": c.cadence,
                "typical_amount": c.typical_amount,
                "occurrences": c.occurrences,
                "next_expected": c.next_expected.isoformat(),
            },
            dedup_key=(
                f"recurring_detected:{c.counterparty_kind}:"
                f"{c.counterparty}:{c.cadence}"
            ),
        ):
            report.recurring_detected += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def on_new_payments(
    payment_ids: Iterable[int], *,
    db_path: Path | str | None = None,
    now: datetime | None = None,
) -> ReactorReport:
    """Process a batch of newly-inserted payments through the core pipeline."""
    report = ReactorReport()
    now_dt = now or datetime.now()

    with connect(db_path) as conn:
        for pid in payment_ids:
            row = conn.execute(
                "SELECT * FROM payments WHERE id = ?", (pid,)
            ).fetchone()
            if not row:
                continue
            try:
                _process_classifier(row, conn, report)
                row = conn.execute(
                    "SELECT * FROM payments WHERE id = ?", (pid,)
                ).fetchone()
                _process_anomalies(row, conn, report)
                _process_goals(row, conn, report, now=now_dt)
                report.payments_processed += 1
            except Exception as e:
                msg = f"reactor error on payment {pid}: {e}"
                report.errors.append(msg)
                log.exception(msg)

        try:
            _process_recurring(conn, report)
        except Exception as e:
            msg = f"recurring detector error: {e}"
            report.errors.append(msg)
            log.exception(msg)

    log.info(report.summary())
    return report


def react_to_all_unprocessed(
    db_path: Path | str | None = None, *, now: datetime | None = None,
) -> ReactorReport:
    """
    Backfill entry point. Processes all payments that have no `categorized`
    event AND no user-set category.
    """
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.id FROM payments p
            LEFT JOIN agent_events e
              ON e.kind = 'categorized' AND e.payment_id = p.id
            WHERE e.id IS NULL
              AND (p.category_source IS NULL OR p.category_source != 'user')
            ORDER BY p.id ASC
            """
        ).fetchall()
        ids = [r[0] for r in rows]
    return on_new_payments(ids, db_path=db_path, now=now)
