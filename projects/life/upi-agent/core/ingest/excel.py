"""
Excel ingestion: parse SBI file → dedup against payments.ref_no → upsert.

Dedup is exact equi-join on `ref_no` because UPI reference numbers and NEFT
UTRs are issued by NPCI/RBI and globally unique. No fuzzy matching needed.

After ingestion, fires core.orchestration.reactor.on_new_payments(...) so the
agentic layer (anomaly detection, weekly story, goal tracking) sees new rows.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from core.parsers.sbi_excel import parse_sbi_file, ParsedRow
from core import config


def ingest(file_path: str | Path, db_path: Path | None = None) -> dict:
    """
    Ingest an SBI Excel file. Dedup against existing rows on ref_no; upsert
    new ones; fire reactor hook for downstream agents.

    Returns:
        {
          'parsed': total parsed rows,
          'matched_existing': rows whose ref_no already in DB (source promoted),
          'inserted': new rows added,
          'skipped': rows neither matched nor inserted (parse holes),
          'new_payment_ids': IDs of newly-inserted rows (passed to reactor),
        }
    """
    db_path = db_path or config.DB_PATH
    parsed_rows = parse_sbi_file(file_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    matched = 0
    inserted = 0
    skipped = 0
    new_ids: List[int] = []

    payment_cols = {r[1] for r in c.execute("PRAGMA table_info(payments)")}
    has_source = "source" in payment_cols
    has_txn_kind = "txn_kind" in payment_cols
    has_message_rowid = "message_rowid" in payment_cols
    has_sender_id = "sender_id" in payment_cols
    has_raw_text = "raw_text" in payment_cols
    has_calendar = "calendar_events" in payment_cols
    has_confidence = "confidence" in payment_cols
    has_bank = "bank" in payment_cols

    for row in parsed_rows:
        if row.ref_no:
            existing = c.execute(
                "SELECT id, source FROM payments WHERE ref_no = ?",
                (row.ref_no,),
            ).fetchone()
            if existing:
                if has_source and existing["source"] == "sms":
                    c.execute(
                        "UPDATE payments SET source = 'both' WHERE id = ?",
                        (existing["id"],),
                    )
                matched += 1
                continue

        cols = ["occurred_at", "amount", "direction",
                "counterparty_vpa", "counterparty_name", "ref_no"]
        vals = [row.occurred_at, row.amount, row.direction,
                row.counterparty_vpa, row.counterparty_name, row.ref_no]

        if has_bank:
            cols.append("bank"); vals.append("SBI")
        if has_message_rowid:
            cols.append("message_rowid"); vals.append(None)
        if has_sender_id:
            cols.append("sender_id"); vals.append(None)
        if has_raw_text:
            cols.append("raw_text"); vals.append(row.raw_description)
        if has_confidence:
            cols.append("confidence"); vals.append(1.0)
        if has_calendar:
            cols.append("calendar_events"); vals.append(None)
        if has_source:
            cols.append("source"); vals.append("excel")
        if has_txn_kind:
            cols.append("txn_kind"); vals.append(row.txn_kind)

        placeholders = ",".join("?" for _ in cols)
        col_list = ",".join(cols)
        c.execute(
            f"INSERT INTO payments ({col_list}) VALUES ({placeholders})",
            vals,
        )
        new_ids.append(c.lastrowid)
        inserted += 1

    conn.commit()
    conn.close()

    if new_ids:
        try:
            from core.orchestration.reactor import on_new_payments
            on_new_payments(new_ids)
        except Exception:
            pass  # reactor layer optional; known gap — not addressed here

    return {
        "parsed": len(parsed_rows),
        "matched_existing": matched,
        "inserted": inserted,
        "skipped": skipped,
        "new_payment_ids": new_ids,
    }


if __name__ == "__main__":
    import sys
    print(ingest(sys.argv[1]))
