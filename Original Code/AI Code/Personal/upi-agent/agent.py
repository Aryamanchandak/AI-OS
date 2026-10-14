"""
UPI payment agent.

Run this daily (or on demand). It:
  1. Opens ~/Library/Messages/chat.db (read-only) — populated by iPhone
     SMS forwarding to your Mac.
  2. Pulls SMS since the last run (tracked in state.json).
  3. Parses UPI messages, filters out OTPs/promos/balance alerts.
  4. For each payment, queries macOS Calendar for events in a ±30-min window
     to enrich context (what you were doing when the payment happened).
  5. Upserts everything into a local SQLite database at ~/.upi-agent/data.db.

Everything is local. No network calls. chat.db is opened in read-only mode.

Usage:
    python3 agent.py              # run ingestion
    python3 agent.py --reset      # wipe state, re-ingest everything
    python3 agent.py --since 30d  # force re-ingest last 30 days
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

try:
    # Package-style import: works when imported as `brain.agent`.
    from .parser import parse, ParsedPayment
except ImportError:
    # Script-style fallback: works when running `python3 agent.py`
    # from inside this directory (legacy CLI use).
    from parser import parse, ParsedPayment  # type: ignore[no-redef]


# --- Paths -------------------------------------------------------------------

DATA_DIR = Path.home() / ".upi-agent"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "data.db"
STATE_PATH = DATA_DIR / "state.json"
CHAT_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"

# macOS "Core Data" / Apple Absolute Time epoch: Jan 1 2001 UTC.
# chat.db message dates are stored as nanoseconds since this epoch
# on 10.13+. We convert to and from UTC datetimes.
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


def apple_ns_to_datetime(apple_ns: int) -> datetime:
    """Convert Apple nanoseconds-since-2001 to a UTC datetime."""
    return APPLE_EPOCH + timedelta(seconds=apple_ns / 1e9)


def datetime_to_apple_ns(dt: datetime) -> int:
    """Convert a UTC datetime to Apple nanoseconds-since-2001."""
    return int((dt - APPLE_EPOCH).total_seconds() * 1e9)


# --- SQLite schema -----------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Stable identity: chat.db message ROWID + reference number if present.
    -- Used for idempotent re-ingestion.
    message_rowid      INTEGER NOT NULL,
    reference          TEXT,
    -- When the payment happened (from SMS timestamp; we treat SMS delivery
    -- time as ≈ payment time, usually within seconds).
    occurred_at        TEXT NOT NULL,        -- ISO 8601 UTC
    -- Financials
    amount             REAL,
    direction          TEXT,                 -- 'debit' | 'credit'
    bank               TEXT,
    -- Counterparty — one or both of these will be set
    counterparty_vpa   TEXT,
    counterparty_name  TEXT,
    account_last4      TEXT,
    -- Provenance
    sender_id          TEXT,
    raw_text           TEXT NOT NULL,
    confidence         REAL NOT NULL,
    -- User annotations (filled in via dashboard later)
    category           TEXT,
    note               TEXT,
    -- Calendar enrichment — JSON array of {title, start, end}
    calendar_events    TEXT,
    -- Housekeeping
    created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(message_rowid)
);

CREATE INDEX IF NOT EXISTS idx_payments_occurred   ON payments(occurred_at);
CREATE INDEX IF NOT EXISTS idx_payments_direction  ON payments(direction);
CREATE INDEX IF NOT EXISTS idx_payments_cp_vpa     ON payments(counterparty_vpa);
CREATE INDEX IF NOT EXISTS idx_payments_category   ON payments(category);
"""


@contextmanager
def open_db(path: Path) -> Iterator[sqlite3.Connection]:
    """Context manager yielding a committed connection to our local DB."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- State (where we left off last run) --------------------------------------

def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"last_message_rowid": 0}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


# --- chat.db reader ----------------------------------------------------------

def read_new_messages(since_rowid: int = 0) -> Iterator[dict]:
    """
    Yield SMS messages from chat.db with ROWID > since_rowid.

    We open in read-only mode (uri=True, mode=ro) so we can't accidentally
    modify iMessage's live database.
    """
    if not CHAT_DB_PATH.exists():
        raise RuntimeError(
            f"chat.db not found at {CHAT_DB_PATH}. "
            "Make sure iMessage + SMS forwarding is set up on this Mac "
            "(iPhone Settings → Messages → Text Message Forwarding)."
        )

    uri = f"file:{CHAT_DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        query = """
            SELECT
              m.ROWID        AS rowid,
              m.text         AS text,
              m.date         AS date_ns,
              h.id           AS sender_id,
              h.service      AS service
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.text IS NOT NULL
              AND m.is_from_me = 0
              AND h.service = 'SMS'
              AND m.ROWID > ?
            ORDER BY m.ROWID ASC
        """
        for row in conn.execute(query, (since_rowid,)):
            yield {
                "rowid": row["rowid"],
                "text": row["text"],
                "occurred_at": apple_ns_to_datetime(row["date_ns"]),
                "sender_id": row["sender_id"] or "",
            }
    finally:
        conn.close()


# --- Calendar enrichment (macOS EventKit via AppleScript) --------------------
#
# We shell out to osascript rather than binding pyobjc EventKit. Reasons:
#  - No extra dependency (osascript ships with macOS).
#  - Permission flow is handled by Calendar.app automatically.
#  - Slow (~0.5s per call) but we run in batches once a day, so it's fine.
#
# First run will prompt: "Terminal wants access to your calendar" — allow it.

CALENDAR_APPLESCRIPT = """
on run argv
    set startDate to (item 1 of argv) as date
    set endDate to (item 2 of argv) as date
    set output to ""
    tell application "Calendar"
        repeat with c in calendars
            try
                set evs to (every event of c whose start date ≥ startDate and start date ≤ endDate)
                repeat with e in evs
                    set output to output & (summary of e) & "\t" & ¬
                        ((start date of e) as string) & "\t" & ¬
                        ((end date of e) as string) & "\n"
                end repeat
            end try
        end repeat
    end tell
    return output
end run
"""


def calendar_events_around(
    occurred_at: datetime, window_minutes: int = 30
) -> list[dict]:
    """Query Calendar.app for events overlapping [occurred_at - W, occurred_at + W]."""
    # Calendar.app wants local-time formatted dates. Convert from UTC.
    local = occurred_at.astimezone()
    start = local - timedelta(minutes=window_minutes)
    end = local + timedelta(minutes=window_minutes)
    # AppleScript date format: "mm/dd/yyyy HH:MM:SS"
    fmt = "%m/%d/%Y %H:%M:%S"

    try:
        result = subprocess.run(
            ["osascript", "-", start.strftime(fmt), end.strftime(fmt)],
            input=CALENDAR_APPLESCRIPT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0:
        return []  # Permission denied or other error — silently skip enrichment.

    events = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            events.append({"title": parts[0], "start": parts[1], "end": parts[2]})
    return events


# --- Upsert ------------------------------------------------------------------

def upsert_payment(
    conn: sqlite3.Connection,
    message_rowid: int,
    occurred_at: datetime,
    parsed: ParsedPayment,
    calendar_events: list[dict],
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO payments (
            message_rowid, reference, occurred_at,
            amount, direction, bank,
            counterparty_vpa, counterparty_name, account_last4,
            sender_id, raw_text, confidence, calendar_events
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_rowid,
            parsed.reference,
            occurred_at.isoformat(),
            parsed.amount,
            parsed.direction,
            parsed.bank,
            parsed.counterparty_vpa,
            parsed.counterparty_name,
            parsed.account_last4,
            parsed.sender_id,
            parsed.raw_text,
            parsed.confidence,
            json.dumps(calendar_events) if calendar_events else None,
        ),
    )


# --- Main --------------------------------------------------------------------

def _parse_since(since: str) -> timedelta:
    """Parse a duration string like '30d', '7d', '24h', '60m'."""
    s = since.strip().lower()
    if s.endswith("d"):
        return timedelta(days=int(s[:-1]))
    if s.endswith("h"):
        return timedelta(hours=int(s[:-1]))
    if s.endswith("m"):
        return timedelta(minutes=int(s[:-1]))
    if s.endswith("w"):
        return timedelta(weeks=int(s[:-1]))
    raise ValueError(f"unrecognized duration: {since!r}. Use e.g. '30d', '24h', '7d'.")


def run(reset: bool = False, since: Optional[str] = None) -> None:
    state = {"last_message_rowid": 0} if reset else load_state()

    # --since flag overrides state: re-read all messages since the given
    # duration. We rely on UNIQUE(message_rowid) + INSERT OR IGNORE to dedupe.
    since_cutoff: Optional[datetime] = None
    if since:
        state["last_message_rowid"] = 0
        since_cutoff = datetime.now(timezone.utc) - _parse_since(since)
        print(f"--since: only ingesting messages after {since_cutoff.isoformat()}")

    since_rowid = state["last_message_rowid"]
    print(f"Reading SMS from chat.db since rowid {since_rowid}...")

    scanned = 0
    parsed_count = 0
    max_rowid = since_rowid
    new_payment_ids: list[int] = []

    with open_db(DB_PATH) as conn:
        for msg in read_new_messages(since_rowid):
            scanned += 1
            max_rowid = max(max_rowid, msg["rowid"])

            # --since filter
            if since_cutoff and msg["occurred_at"] < since_cutoff:
                continue

            parsed = parse(msg["text"], sender_id=msg["sender_id"])
            if parsed is None:
                continue

            # Enrich with calendar events around this payment.
            events = calendar_events_around(msg["occurred_at"])

            upsert_payment(
                conn,
                message_rowid=msg["rowid"],
                occurred_at=msg["occurred_at"],
                parsed=parsed,
                calendar_events=events,
            )
            # If the upsert was a real insert (not an IGNORE on duplicate),
            # collect the id for the reactor.
            if conn.total_changes and conn.execute(
                "SELECT changes()"
            ).fetchone()[0] > 0:
                pid = conn.execute(
                    "SELECT id FROM payments WHERE message_rowid = ?",
                    (msg["rowid"],),
                ).fetchone()
                if pid:
                    new_payment_ids.append(pid[0])

            parsed_count += 1
            cp = parsed.counterparty_vpa or parsed.counterparty_name or "?"
            amt = f"Rs.{parsed.amount:,.2f}" if parsed.amount else "?"
            ctx = f" [{events[0]['title']}]" if events else ""
            print(f"  ✓ {msg['occurred_at']:%Y-%m-%d %H:%M} "
                  f"{parsed.direction or '?':<6} {amt:>12} → {cp}{ctx}")

    state["last_message_rowid"] = max_rowid
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    print(f"\nScanned {scanned} messages, stored {parsed_count} payments.")
    print(f"State saved. Data at {DB_PATH}.")

    # Hand off to the brain. Failures here must NOT break ingestion — the
    # ledger is the source of truth, the brain is decoration.
    if new_payment_ids:
        try:
            from core.orchestration.reactor import on_new_payments
            report = on_new_payments(new_payment_ids, db_path=DB_PATH)
            print(report.summary())
        except Exception as e:
            import traceback
            print(f"WARNING: brain reactor failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="Wipe state and re-ingest from the beginning")
    ap.add_argument("--since", default=None,
                    help="Re-read messages newer than this duration "
                         "(e.g. '30d', '7d', '24h', '60m')")
    args = ap.parse_args()

    try:
        run(reset=args.reset, since=args.since)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
