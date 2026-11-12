"""
Unified schema migrations — merged from brain/migrate.py and tax/migrate.py.

All steps are idempotent: safe to run repeatedly. Called lazily by
core.schema.db.connect on first connection, and explicitly via
`python -m core.cli migrate`.

Migration order:
  1. PRAGMA foreign_keys = ON
  2. Verify payments table exists (raises RuntimeError — not sys.exit)
  3. Add columns to payments if missing: source, txn_kind, category_source
  4. CREATE tables: agent_events, goals, goal_status_cache, category_rules
     (brain schema with last_seen), recurring_payments, buckets, tax_settings
  5. Seed tax_settings defaults
  6. Create indexes
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


REQUIRED_PAYMENT_COLS = {
    "id", "occurred_at", "amount", "direction",
    "counterparty_vpa", "counterparty_name", "category",
}

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS agent_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL,
    kind          TEXT    NOT NULL,
    payment_id    INTEGER,
    severity      INTEGER NOT NULL DEFAULT 0,
    title         TEXT    NOT NULL,
    explanation   TEXT    NOT NULL,
    payload_json  TEXT,
    acknowledged  INTEGER NOT NULL DEFAULT 0,
    dedup_key     TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_events_kind        ON agent_events(kind);
CREATE INDEX IF NOT EXISTS idx_events_created_at  ON agent_events(created_at);
CREATE INDEX IF NOT EXISTS idx_events_payment_id  ON agent_events(payment_id);
CREATE INDEX IF NOT EXISTS idx_events_unack       ON agent_events(acknowledged);

CREATE TABLE IF NOT EXISTS goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    description TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    spec_json   TEXT    NOT NULL,
    scope       TEXT    NOT NULL,
    start_date  TEXT    NOT NULL,
    end_date    TEXT,
    status      TEXT    NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);

CREATE TABLE IF NOT EXISTS goal_status_cache (
    goal_id     INTEGER PRIMARY KEY,
    state       TEXT    NOT NULL,
    progress    REAL    NOT NULL DEFAULT 0,
    message     TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS category_rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key_kind   TEXT    NOT NULL,
    key_value  TEXT    NOT NULL,
    category   TEXT    NOT NULL,
    hits       INTEGER NOT NULL DEFAULT 1,
    last_seen  TEXT,
    UNIQUE (key_kind, key_value, category)
);

CREATE INDEX IF NOT EXISTS idx_rules_lookup ON category_rules(key_kind, key_value);

CREATE TABLE IF NOT EXISTS recurring_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    counterparty    TEXT    NOT NULL,
    counterparty_kind TEXT  NOT NULL,
    cadence         TEXT    NOT NULL,
    typical_amount  REAL    NOT NULL,
    occurrences     INTEGER NOT NULL,
    first_seen      TEXT    NOT NULL,
    last_seen       TEXT    NOT NULL,
    next_expected   TEXT,
    payment_ids     TEXT    NOT NULL,
    UNIQUE (counterparty, counterparty_kind, cadence)
);

CREATE INDEX IF NOT EXISTS idx_recurring_last_seen ON recurring_payments(last_seen);

CREATE TABLE IF NOT EXISTS buckets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS tax_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _add_payments_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(payments)")}
    if "source" not in cols:
        conn.execute("ALTER TABLE payments ADD COLUMN source TEXT DEFAULT 'sms'")
        conn.execute("UPDATE payments SET source = 'sms' WHERE source IS NULL")
    if "txn_kind" not in cols:
        conn.execute("ALTER TABLE payments ADD COLUMN txn_kind TEXT DEFAULT 'upi'")
        conn.execute("UPDATE payments SET txn_kind = 'upi' WHERE txn_kind IS NULL")
    if "category_source" not in cols:
        conn.execute("ALTER TABLE payments ADD COLUMN category_source TEXT")
    if "ref_no" not in cols:
        conn.execute("ALTER TABLE payments ADD COLUMN ref_no TEXT")


def migrate(db_path: Path | str) -> None:
    """Run all migrations against db_path. Safe to call repeatedly."""
    path = Path(db_path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(payments)")}
        missing = REQUIRED_PAYMENT_COLS - existing_cols
        if missing:
            raise RuntimeError(
                f"payments table is missing required columns: {missing}. "
                "Run the base agent first to create the schema."
            )

        _add_payments_columns(conn)
        conn.executescript(_TABLES_SQL)

        # Seed tax_settings defaults
        conn.execute("INSERT OR IGNORE INTO tax_settings VALUES ('mode', 'manual')")
        conn.execute("INSERT OR IGNORE INTO tax_settings VALUES ('llm_endpoint', '')")
        conn.execute("INSERT OR IGNORE INTO tax_settings VALUES ('llm_model', '')")

        # Indexes for ingest dedup and triage queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_ref_no ON payments(ref_no)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_category ON payments(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_txn_kind ON payments(txn_kind)")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    from core.config import DB_PATH
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    migrate(DB_PATH)
    print(f"Migrations applied to {DB_PATH}")
