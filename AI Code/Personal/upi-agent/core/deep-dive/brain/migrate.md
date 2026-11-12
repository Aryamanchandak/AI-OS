# migrate.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 139
**Language:** Python

---

## What This File Does (Plain English)

This file defines and applies the brain layer's database schema. It creates five tables and four indexes that the brain owns, and adds one column (`category_source`) to the `payments` table that is owned by the base agent. Every statement is idempotent — `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, and a PRAGMA inspection before `ALTER TABLE` — so running this repeatedly on an existing database is always safe.

---

## How It Actually Works

### Entry Points

- `migrate(db_path)` — called by `db.py` on first connection per path. Also callable directly: `python -m brain.migrate`.
- Module `if __name__ == "__main__":` block — runs migrations against `config.DB_PATH` when executed directly.

### Data Flow

```
migrate(db_path)
  → open raw sqlite3.Connection (no row_factory needed here)
  → PRAGMA foreign_keys = ON
  → executescript(NEW_TABLES_SQL)   # creates 5 tables + 4 indexes, all IF NOT EXISTS
  → _ensure_payments_column(conn)   # adds category_source to payments if missing
  → commit
  → close
```

### State Management

No in-module state. The DB file on disk is the state. Safe to call from multiple processes simultaneously — SQLite handles the locking, and IF NOT EXISTS makes all DDL no-ops if already applied.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `migrate(db_path)` | Applies all DDL to the target DB file. Opens its own connection separate from `db.connect()`. |
| `_ensure_payments_column(conn)` | Reads `PRAGMA table_info(payments)` and adds `category_source TEXT` only if the column is absent. |

### Tables Created

| Table | Purpose |
|---|---|
| `agent_events` | All brain outputs — categorization, anomalies, goal events, weekly stories, recurring detections. One row per event. Has a `UNIQUE dedup_key` column enforcing idempotency. |
| `goals` | User-declared goals (avoid_merchant, budget_cap, frequency_cap). |
| `goal_status_cache` | Cached evaluation of each active goal. Refreshed daily or on new payments. Has a `FOREIGN KEY → goals(id) ON DELETE CASCADE`. |
| `category_rules` | Learned VPA → category and name_token → category mappings. Upserted when user corrects a category. |
| `recurring_payments` | Detected recurring payment clusters. Upserted by `recurring.refresh_recurring()`. |

### Column Added to `payments` (base-agent table)

| Column | Type | Purpose |
|---|---|---|
| `category_source` | `TEXT` | `'user'` when manually set, `'agent'` when auto-classified, `NULL` when uncategorized. Used by reactor to protect user corrections from being overwritten. |

### External Dependencies

- `sqlite3` (stdlib)
- `brain.config` — only for the `__main__` block (reads `DB_PATH`)

### Error Handling

- If `executescript()` fails, the connection is closed in the `finally` block but no rollback is attempted. `executescript()` auto-commits before running, so partial DDL application is possible on failure (though in practice DDL is atomic in SQLite).
- If `payments` table doesn't exist yet (first run before any ingestion), `PRAGMA table_info(payments)` returns zero rows — `"category_source" not in cols` evaluates True — and the `ALTER TABLE` fails because the table doesn't exist. This is a real bug: running `migrate` before the base agent has ever ingested data will crash here.

---

## Non-Technical Decisions Embedded in the Code

- The brain deliberately does not own the `payments` table — it only borrows one column. This is a conscious separation of concerns: the base agent (`agent.py`) is the source of truth for raw payment data.
- `executescript()` is used instead of individual `execute()` calls, which means SQLite auto-commits before running the script. There is no explicit rollback path if any individual DDL statement fails partway through. This is acceptable because all DDL is `IF NOT EXISTS`.
- The `dedup_key` column on `agent_events` has a `UNIQUE` constraint at the DB level. This is the idempotency mechanism — the reactor uses `INSERT OR IGNORE` with this key.
- `goal_status_cache` has an `ON DELETE CASCADE` foreign key to `goals`. If a goal is deleted from the `goals` table, its cache row is deleted automatically. However, goals are only ever `status`-updated to `'ended'` — they are never actually deleted from the table. So the cascade never fires in practice.

---

## Honest Gaps and Risks

- Running `migrate()` before any payments have been ingested (before `agent.py` has created the `payments` table) will raise a `sqlite3.OperationalError` in `_ensure_payments_column`. The `PRAGMA table_info` call returns empty, the alter-table is attempted, and it fails because the table doesn't exist. `db.py` calls migrate on first connect, so the first `with connect() as conn:` in a fresh install will crash.
- `executescript()` auto-commits, meaning the migration is not atomic with the subsequent `_ensure_payments_column()` call. If the process is killed between them, the tables exist but `category_source` is absent — the next run will add the column correctly, so the end state is consistent, but it's not a clean transaction.
- There is no version tracking (no schema version table or migrations table). There is no way to know which migrations have been applied. Adding a new migration requires adding it to `NEW_TABLES_SQL` and ensuring it's `IF NOT EXISTS` — there is no ordered migration system.

---

## Developer Notes

- When adding a new brain table, add it to `NEW_TABLES_SQL` with `CREATE TABLE IF NOT EXISTS`. Do not create a separate migration function.
- If you need to add a column to an existing brain table (not `payments`), use the same `PRAGMA table_info` + `ALTER TABLE IF NOT EXISTS` pattern used for `category_source`. SQLite does not support `ADD COLUMN IF NOT EXISTS` natively before version 3.37 — use the PRAGMA inspection pattern.
- The `payments` table is created by `agent.py` (the base agent), not this file. Never add the `payments` creation here; doing so would create an empty payments table before the agent can populate it, which may confuse the dedup logic in the base agent.
