# db.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 63
**Language:** Python

---

## What This File Does (Plain English)

This file provides the one connection helper used by every brain module that touches SQLite. It wraps `sqlite3.connect()` in a context manager that auto-commits on success, rolls back on exception, and runs schema migrations exactly once per database path per process. Every brain module that needs the database calls `with connect() as conn:` and gets back a `sqlite3.Row`-enabled connection.

---

## How It Actually Works

### Entry Points

- `connect(db_path=None)` — context manager yielding a `sqlite3.Connection`. Called by `reactor.py`, `narrator.py`, `notifier.py`, `classifier.py`, `goals.py`, and `cli.py`.
- `reset_migration_cache()` — test helper only, not used in production.

### Data Flow

```
caller invokes connect()
  → resolve path (config.DB_PATH if not provided)
  → if path not in _MIGRATED:
      create parent directories
      call migrate.migrate(path)   # idempotent schema setup
      add path to _MIGRATED
  → open sqlite3.Connection
  → set row_factory = sqlite3.Row
  → enable PRAGMA foreign_keys = ON
  → yield connection to caller
  → on exit: commit (success) or rollback (exception)
  → close connection
```

### State Management

`_MIGRATED: set[str]` is a module-level set. Once a database path has had migrations run, it is added to this set and migrations are skipped on every subsequent `connect()` call in the same process. This is an in-process cache — if two separate processes open the same DB, both will run migrations independently (which is safe because `migrate.py` is idempotent).

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `connect(db_path)` | Context manager: migrates once, opens connection with Row factory + FK enforcement, auto-commits or rolls back |
| `reset_migration_cache()` | Clears `_MIGRATED` — only useful in tests that want a fresh migration pass on an in-memory DB |

### External Dependencies

- `sqlite3` (stdlib)
- `brain.config` — reads `config.DB_PATH` as the default path
- `brain.migrate` — calls `migrate.migrate()` on first connection per path

### Error Handling

- Migration errors propagate uncaught — if `migrate.migrate()` fails, the `connect()` context manager raises before yielding.
- SQL errors inside the `with connect() as conn:` block cause `conn.rollback()` then re-raise.
- `conn.close()` is in a `finally` block, so the connection is always closed even if rollback fails.

---

## Non-Technical Decisions Embedded in the Code

- The process-level migration cache (`_MIGRATED`) avoids running `PRAGMA table_info` on every connection, which would add latency to high-frequency callers. The tradeoff is that if the DB file is replaced between connections in the same process, the replacement will not be migrated. This is an acceptable tradeoff for a single-user agent that doesn't swap databases at runtime.
- `PRAGMA foreign_keys = ON` is set on every connection. Foreign keys are off by default in SQLite; without this the `goal_status_cache → goals` cascade delete would silently not work.
- `row_factory = sqlite3.Row` is set so callers can access columns by name (`row["amount"]`) rather than index. This is relied upon throughout all brain modules.
- The connection is opened fresh for every `with connect()` call — there is no connection pooling. This is fine for the agent's single-process, infrequent-access pattern.

---

## Honest Gaps and Risks

- `_MIGRATED` is a module-level global. In test suites, if tests share a process and use the same DB path, the first test to connect will run migrations and subsequent tests won't — even if those tests want a clean migration pass. `reset_migration_cache()` exists to solve this but callers must remember to use it.
- There is no WAL mode (`PRAGMA journal_mode = WAL`). If the dashboard and the agent run simultaneously and both write, they will block each other on write locks. For a single-user localhost app this is unlikely to cause visible problems, but it is a latent risk.
- The `db_path` parameter accepts `Path | str | None` but the type coercion (`Path(db_path) if db_path else config.DB_PATH`) means an empty string `""` is treated as a truthy `Path("")` rather than falling back to the default. This would open a file named `""` in the current directory, which would fail with an OS error.

---

## Developer Notes

- All brain modules must use `connect()` from this file — never call `sqlite3.connect()` directly in a brain module. This ensures migrations run and `row_factory` is always set.
- Tests that use an in-memory DB (`:memory:`) should call `reset_migration_cache()` before each test to ensure migrations run cleanly on the fresh DB.
- The auto-commit/rollback behaviour means you cannot do multi-statement transactions that span multiple `with connect()` blocks. Each block is one transaction.
