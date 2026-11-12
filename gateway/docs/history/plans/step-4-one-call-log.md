# Step 4: One Call Log, One YAML Adapter, One SQLite Helper

**Why.** Each call is recorded in three places: an in-memory `Meter` (lost on restart, read by `/calls` and `/cost/*`), the audit table (left over from channels, one JSON blob per call), and the ledger (proper columns, never written). YAML loading is copied in about seven places, and SQLite is opened two ways.

**Done when.** Every chat and embed call writes one ledger row, and `/calls`, `/cost/by_agent` and `/cost/by_principal` read from the ledger, so their numbers survive a restart. `Meter` and the `audit/` package are gone. Only `src/gateway/config.py` imports `yaml`. SQLite is opened only through `SQLiteDatabase`. Tests pass and you've seen the output.

**Decided.** The ledger is the single call log (corrects the original review). `GLCPaths.load_mapping` becomes the one YAML loader. Reading calls back by session moves to the ledger.

**Answer before starting (defaults in brackets).** OK the new file `src/gateway/config.py` [yes]. Old `audit.sqlite`: delete or leave on disk [leave]. If the ledger write fails, does the call fail [yes, fail closed: no unlogged spend].

**Tests first.** One chat call adds exactly one ledger row with provider, model, tokens, USD, agent, session and profile; one embed call adds one row. Restart test: call, rebuild the app on the same database, `/calls` still shows it (fails today). `/cost/by_agent` equals the sum of rows. `config.load_mapping` gives a clear error for a missing, malformed or non-mapping file (brings back the check removed in step 1). A failed ledger write fails the call.

**Main changes.** Move `load_mapping` into `config.py`; switch pricing, budget, profiles, registry and service to it. Budget uses `SQLiteDatabase`. In the ledger, define the column list once, drop columns for features that don't exist (tenant, project, user, router_decision, escalations, tier, call_role, cache_*, tokens_saved, usd_saved, embed_dim), add `rollup()` and `recent()`. Finalization and embed write to the ledger. Delete `audit/`, and `meter.py` if `Principal`/`DIMENSIONS` fit in `budget.py`. Audit-only test functions are replaced by the ledger versions and listed by name first.

**Verify.** `grep -rln "import yaml" src` → only `config.py`. `grep -rn "AuditStore\|Meter(\|sqlite3.connect" src` → only `platform/database/__init__.py`.

Commit: `git add -A .` then `git commit -m "Shrink step 4: ledger as the single call log; one YAML adapter"`.
