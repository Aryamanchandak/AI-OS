# Shared SQLite helper

The implementation lives in `__init__.py`. `SQLiteDatabase` centralizes connection setup and cleanup for the [call ledger](../../ledger/README.md) and the budget controller. It is the only place that opens SQLite.

`connect()` creates the parent directory when necessary, opens a connection with named-row access, and closes it when the context exits. Normal connections commit on success and roll back on exceptions. An explicit `autocommit=True` mode lets callers make each statement durable immediately.

`migrate()` executes supplied SQL scripts inside that connection lifecycle. Schemas and migration statements belong to the calling domain; this helper does not track a universal schema version or provide a connection pool. The budget controller currently manages its own SQLite connections because it needs explicit atomic reservation transactions.
