# `tax/migrate.py`

**Lines:** 116

## Purpose

Applies the tax module's schema additions to an already-initialised `data.db`. It adds columns to `payments`, creates three tables (`buckets`, `tax_settings`, `category_rules`), seeds `tax_settings` with defaults, and adds performance indexes. Every operation uses `IF NOT EXISTS` or column-existence checks, making the file safe to run multiple times.

## Entry Point

`migrate(db_path)` — called by `brain.db` lazily on first connect, or manually (`python migrate.py`).

## Data Flow

1. Checks `db_path` exists; exits with code 1 if not.
2. Queries `PRAGMA table_info(payments)` to get existing columns.
3. Validates `REQUIRED_PAYMENT_COLS` are present; exits with code 1 if any are missing.
4. For each of `source`, `txn_kind`, `category_source`: issues `ALTER TABLE ADD COLUMN` if not already present.
5. Issues `CREATE TABLE IF NOT EXISTS` for `buckets`, `tax_settings`, `category_rules`.
6. Inserts default rows into `tax_settings` with `INSERT OR IGNORE`.
7. Creates indexes on `payments(ref_no)`, `payments(category)`, `payments(txn_kind)`.
8. Commits and closes.

## Schema Added

| Object | Type | Purpose |
|---|---|---|
| `payments.source` | TEXT DEFAULT 'sms' | Tracks whether row came from SMS, Excel, or both |
| `payments.txn_kind` | TEXT DEFAULT 'upi' | Transaction type (upi/neft/imps/reversal/etc.) |
| `payments.category_source` | TEXT | Who set the category: 'user', 'auto', or NULL |
| `buckets` | Table | User-defined classification buckets (name + archived_at) |
| `tax_settings` | Table | Key-value store: mode, llm_endpoint, llm_model |
| `category_rules` | Table | Learned VPA/name → bucket mappings with hit counts |

## Design Decisions

- The `category_rules` table is defined here as a fallback in case the brain layer (`brain/migrate.py`) hasn't been run yet. Both files create this table with `CREATE TABLE IF NOT EXISTS` — whichever runs first wins.
- Default mode is `'manual'`, meaning no LLM is used unless the user explicitly switches to `'ai'` in settings.

## Known Gaps / Risks

- **Coupling assumption:** `REQUIRED_PAYMENT_COLS` includes `category`, which is added by the base agent's schema. If `agent.py` or `brain/migrate.py` hasn't run first, this migration exits with an error. The ordering dependency is undocumented at the call site.
- `sys.exit(1)` inside a library function will terminate the entire process if the caller is `dashboard.py` or a test. A raised exception would be safer for library usage.
- The `category_source` column is noted as "used by base + brain layer" but the base schema creation in `agent.py` does not appear to define it — `tax/migrate.py` is the only place it is created, creating an implicit dependency direction that runs the wrong way.
