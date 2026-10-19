# Call ledger

This folder holds the one record of every LLM call. `repository.py` implements `CallLedger`; `__init__.py` exports it.

`COLUMNS` is the single column list; the table, the migration for older database files and every insert are built from it. Chat finalization and the embed path each `append()` one row per call. A failed write raises, so the call fails rather than leaving spend unlogged. `recent()` feeds `/api/llm/calls`, `rollup()` feeds `/cost/by_agent` and `/cost/by_principal`, and `by_provider()` feeds the `today` totals. Because rows live in SQLite, all of these survive a restart.

The [application lifespan](../app/README.md) builds it from `GLCPaths.ledger_db`. The budget controller keeps its own tables in the same database file.
