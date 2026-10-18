# Step 0: Commit the Pending Work

## Why
The gateway folder has uncommitted changes from earlier cleanup sessions. They include files moved into `contracts/`, `scripts/`, `docs/` and `tests/`, and 21 new README files. Step 1 should start from a clean snapshot, so its own changes are easy to see and easy to undo.

## Definition of done
- `git status`, run from inside `gateway/`, shows nothing to commit.
- The full test suite passes on that snapshot, and you've seen the output.

## Decisions already made
- Commit only the gateway folder. The pending changes outside it stay as they are; that's your call: `../shell/package.json`, `../Ingestion 2/…` and `../Old Code/`.

## Open questions
- None.

## What's pending (snapshot from 2026-10-18)
- **Deleted at the gateway root:** `DEPENDENCIES.md`, `GATEWAY_REQUIREMENTS.md`, `conftest.py`, `export_openapi.py`, `openapi.json`. These were moved to `docs/dependencies.md`, `tests/conftest.py`, `scripts/export_openapi.py` and `contracts/openapi.json`.
- **Changed:** `README.md`, `src/gateway/llm/providers/README.md`, `tests/test_contract_staleness.py`, `tests/test_llm_contract.py`, `tests/test_restored_contracts.py`.
- **New:** `contracts/`, `docs/` (including these plans), `scripts/`, `tests/conftest.py`, and 21 README files under `src/gateway/`.

## Steps
1. Run the tests:
   ```
   .venv/bin/pytest -q
   ```
   This runs every test. If anything fails, stop. Don't commit a broken snapshot.
2. Check that nothing secret or generated is about to be committed:
   ```
   git status --short .
   git check-ignore -v src/ai_os_gateway.egg-info
   ```
   The first command lists the changes in this folder only. The second should report that the build folder is ignored. **Look for a `.env` file in the list. If one appears, stop.** (Step 5 adds `.env` to `.gitignore`.)
3. Commit (you run these, from the `gateway` folder):
   ```
   git add -A .                                   # stage every change inside gateway/ only (the dot means "this folder")
   git commit -m "Gateway: commit moved files, READMEs and review docs"   # save the snapshot
   git status --short .                           # should print nothing
   ```

## Not in this step
- Any code change.
