# Step 3: Mechanical Batch — Commit 1–2c, Remove Non-LLM Features

Nothing here needs a decision. The gateway is trunk, so it still needs your one OK before it runs. It ends in **two commits**, one per part.

## Part A: commit steps 1–2c

Steps 1, 2a, 2b and 2c are mixed in one uncommitted tree and share files (`models.py`, `routes.py`, `pipeline.py`, `meter.py`), so they can't be split back into four commits. **This breaks "one task per commit"; confirm you accept one combined commit.** Run `.venv/bin/pytest -q`, check `git status --short .` shows no `.env`, then:

```
git add -A .     # stage every change inside gateway/ (code + these plans)
git commit -m "Shrink steps 1-2c: dead code, providers, streaming/cache, unused request features"
```

## Part B: remove non-LLM features

The gateway's job is LLM calls only, and you've said there's no UI for now. Remove: the `/v1/...` addresses, shell file serving (`SHELL_DIST`, `/assets`, catch-all), `/healthz`, `/dashboard`, `/api/diagnostics/services`, the `agent_trace` forwarder, and the service registry with `config/services.yaml`. Keep `/health` (no token) and the `/api` 404 catch-all. Keep `/traces/*` and `/refusals` until step 6.

Defaults taken as decided: the agent runtime on port 8113 is a leaf, so the trunk must not call it; nothing uses port 8111 (`glc_legacy`), since nothing has worked end to end yet.

**Files touched:** `src/gateway/app/` (`main.py`, `lifespan.py`, `dependencies.py`, `router_registry.py`), root `main.py`, `llm/api/routes.py` and `__init__.py` (drop `alias_registration`), `platform/observability/routes.py`, `platform/service_registry/` (delete), `config/services.yaml` (delete), the READMEs that mention any of these, and `contracts/openapi.json` (regenerated).

**Tests first** (should fail before the change): any `/v1` address, `/`, `/dashboard`, `/healthz`, `/api/diagnostics/services` and `/api/observability/agent_trace/x` return 404; the existing `/health` test still passes.

**Test deletions you're OK-ing:** test functions for `/v1` aliases, the shell, `/healthz`, diagnostics, `agent_trace` and the registry (in `test_llm_contract.py`, `test_main.py`, `test_foundation.py`, `test_restored_contracts.py`, `test_standalone_bootstrap.py`). Possibly **all of `tests/test_foundation.py`**; I'll show you what's left in it before deleting the whole file.

**Verify:** pytest before and after, regenerate the contract with `.venv/bin/python scripts/export_openapi.py`, and `grep -rn "SHELL_DIST\|alias_registration\|healthz\|agent_trace\|service_registry" src tests config main.py` finds nothing.

```
git add -A .
git commit -m "Shrink step 3: remove non-LLM features (v1 aliases, shell, registry)"
```
