# Step 4: One Call Log, One YAML Adapter, One SQLite Helper

## Why
Each LLM call is recorded in three places today:
- **an in-memory list** (`Meter`), lost on every restart, which `/calls` and `/cost/*` read from;
- **the audit table**, built for the old channels work, which squeezes each call into one JSON text field;
- **the ledger**, which has proper columns but is never written to.

Loading YAML files is copied in about seven places, and SQLite is opened two different ways. This step merges each job into one place, so spend survives a restart and each module does one job.

## Definition of done
- Every chat and embed call writes **one row to the ledger**. `/calls`, `/cost/by_agent` and `/cost/by_principal` read from the ledger, so their numbers survive a restart.
- The `Meter` class and the whole `audit/` package are gone.
- Every YAML file is loaded through `src/gateway/config.py`. **Nothing else imports `yaml`.**
- SQLite is opened only through `SQLiteDatabase`.
- The full test suite passes, and you've seen the output.

## Decisions already made
- The ledger is the single call log, not the audit table. This corrects the original review (see `docs/yagni-review-followup.md`).
- `GLCPaths.load_mapping` becomes the one YAML loader.
- `AuditStore.query`'s idea, reading calls back filtered by session, moves to the ledger.

## Open questions (answer before the step starts)
1. **New file:** `src/gateway/config.py`, the single YAML adapter. Your rules say to ask before adding a file, so please OK it.
2. **Existing data:** `audit.sqlite` may hold old rows. Delete the file, or leave it on disk untouched? The default is to leave it; the code simply stops using it.
3. **When writing the call log fails, should the call fail?** Today, a failed audit write fails the request ("fail closed"). The default is to keep that rule for the ledger: no unlogged spend.

## Tests first
- One chat call (with a fake provider) adds exactly one ledger row, with provider, model, tokens, USD cost, agent, session and profile filled in.
- One embed call adds one ledger row.
- **Restart test:** make a call, build a new app on the same database file, and `/api/llm/calls` still shows the call. Today this fails.
- `/cost/by_agent` totals match the sum of the ledger rows.
- `config.load_mapping` raises a clear error for a missing file, a malformed file and a file that isn't a key–value mapping. This brings back the check deleted in step 1.
- If the ledger write fails, the chat call fails (fail-closed).

## Files changed

| File | Change |
|---|---|
| `src/gateway/config.py` | **New file**, about 20 lines: `load_mapping(path)`, moved from `GLCPaths`. The only file that imports `yaml`. |
| `src/gateway/platform/configuration/glc.py` | Remove `load_mapping` and `audit_db` |
| `src/gateway/llm/economics/pricing.py`, `budget.py`, `src/gateway/llm/profiles/__init__.py`, `src/gateway/llm/providers/registry.py`, `src/gateway/llm/service.py` | Use `config.load_mapping` instead of `yaml.safe_load` |
| `src/gateway/llm/economics/budget.py` | Open SQLite through `SQLiteDatabase`, replacing its own `_connect` |
| `src/gateway/ledger/repository.py` | Define the column list once. **Remove** the second copy in `_migrate_columns` (the database file has no real data yet, since nothing ever wrote to it). Drop the columns for features that don't exist: `tenant`, `project`, `user`, `router_decision`, `escalations`, `tier`, `call_role`, `cache_*`, `tokens_saved`, `usd_saved`, `embed_dim`. Add `rollup(dimension, since, value)` and `recent(limit, provider, status, session)`. |
| `src/gateway/llm/orchestration/finalization.py` | Write to the ledger, not to the meter and audit |
| `src/gateway/llm/service.py` | Take the ledger instead of the meter and audit. Embed calls record to the ledger. |
| `src/gateway/llm/api/routes.py` | `/calls`, `/cost/*` and the "today" totals read from the ledger |
| `src/gateway/llm/economics/meter.py` | Keep only `Principal` and `DIMENSIONS`, or move them into `budget.py` and **delete the file**. Decide at the start of the session by which is smaller. |
| `src/gateway/audit/` (`store.py`, `__init__.py`, `README.md`) | **Delete the folder** |
| `src/gateway/app/lifespan.py`, `src/gateway/app/dependencies.py` | Remove the audit store. Pass the ledger to `LLMService`. |
| `src/gateway/ledger/README.md`, `src/gateway/llm/economics/README.md`, `src/gateway/llm/api/README.md`, `src/gateway/README.md` | Update the wording |
| `tests/test_platform_security_control.py`, `tests/test_llm.py`, `tests/test_llm_orchestration.py`, `tests/test_restored_contracts.py` | Switch audit and meter checks to ledger checks. Add the new tests. |
| `docs/dependencies.md` | Note that `pyyaml` now sits behind `config.py` |

## Test files to delete
- None as whole files.
- **Audit-only test functions**, for example the fail-closed audit tests. They're replaced by the ledger versions above, and will be listed by name at the start of the session.

## Not in this step
- An adapter for `httpx` (step 6 removes most of its uses).
- An adapter for OpenTelemetry (step 6).

## Verification
1. Run `.venv/bin/pytest -q` before starting, and record the result.
2. Add the new tests and confirm they fail; the restart test especially.
3. Make the changes. Run `.venv/bin/pytest -q`; all should pass. Show the output.
4. Run `grep -rln "import yaml" src`. Expect only `src/gateway/config.py`.
5. Run `grep -rn "AuditStore\|Meter(\|sqlite3.connect" src`. Expect only `platform/database/__init__.py`.

## Commit
```
git add -A .                                              # stage every change in gateway/
git commit -m "Shrink step 4: ledger as the single call log; one YAML adapter"   # save the snapshot
```
