# Persistent call ledger repository

This folder defines the SQLite repository for per-call accounting history. `repository.py` implements `CallLedger`; `__init__.py` exports it.

Construction creates the `calls` table and indexes, then adds missing columns needed by older database files. The schema includes provider/model, token usage, latency, errors, attribution dimensions, pricing, caching, profile, and legacy routing fields. `append()` accepts a subset of these fields and inserts a timestamped call row. `recent()` reads newest rows; `healthcheck()` verifies that the table can be queried.

The [application lifespan](../app/README.md) constructs and checks this repository using `GLCPaths.ledger_db`. The budget controller also stores its separate budget tables in that database file.

The current LLM finalization path does **not** call `CallLedger.append()`: it writes usage into the in-memory `Meter` and durable `AuditStore`. Consequently, `/api/llm/calls` reads the meter rather than this repository. Having a ledger in the dependency container does not mean all current LLM calls are being inserted into `calls`.
