# Step 3: Remove Non-LLM Features

## Why
The gateway's job is LLM calls only. It also does other jobs:
- it serves the shell's web pages,
- it keeps every route under a second, old `/v1` address,
- it has legacy health and dashboard routes,
- it forwards trace requests to the agent runtime,
- it keeps a list of other services' ports.

You've decided there's no UI for now, so none of these is needed.

## Definition of done
- Gone: the `/v1/...` addresses, shell file serving, `/healthz`, `/dashboard`, `/api/diagnostics/services` and the `agent_trace` forwarder.
- `/health` still works and still needs no token.
- The service registry is gone, or reduced to nothing more than the gateway's own address. Which one depends on what still reads it at the start of the session.
- The full test suite passes, and you've seen the output.

## Decisions already made
- No UI for now. If you later connect one, it serves its own files as a leaf.
- Keep `/health`.

## Open questions (answer before the step starts)
1. **Is the agent runtime (port 8113) a leaf?** If yes, the trunk must not call it, and `agent_trace` goes. That's the default.
2. **Does anything still use port 8111** (`glc_legacy` in `config/services.yaml`)? The default is "no, remove it". Nothing has worked end to end yet, so no real caller can exist.

## Tests first
- `GET /v1/chat/profiles/x` (any `/v1` address) returns 404 ("not found").
- `GET /`, `GET /dashboard`, `GET /healthz` and `GET /api/diagnostics/services` return 404.
- `GET /health` returns `{"status": "ok"}` without a token. This test exists already; keep it.
- `GET /api/observability/agent_trace/x` returns 404.

## Files changed

| File | Change |
|---|---|
| `src/gateway/app/main.py` | Remove `SHELL_DIST`, the `/assets` mount and the shell catch-all route. Remove `/dashboard`, `/healthz`, `_diagnostics_registration` and the `/v1` catch-all. Keep the `/api` 404 catch-all and `/health`. |
| `main.py` (gateway root) | Stop re-exporting `SHELL_DIST` |
| `src/gateway/app/router_registry.py` | Stop registering `alias_registration()`. Drop the `deprecated` option if nothing else uses it. |
| `src/gateway/llm/api/routes.py` | Remove `alias_registration` |
| `src/gateway/llm/api/__init__.py` | Remove the `alias_registration` export |
| `src/gateway/platform/observability/routes.py` | Remove `agent_trace` and the legacy `/v1` registration. Keep `/traces/*` and `/refusals` until step 6. |
| `src/gateway/platform/service_registry/` (`registry.py`, `__init__.py`, `README.md`) | **Delete**, if nothing reads it after the removals above. Today only `/healthz`, the diagnostics route and `agent_trace` read it. |
| `config/services.yaml` | **Delete** along with the registry |
| `src/gateway/app/lifespan.py`, `src/gateway/app/dependencies.py`, `src/gateway/app/main.py` | Remove the service-registry parameter, field and dependency |
| `src/gateway/app/README.md`, `src/gateway/platform/README.md`, `src/gateway/README.md`, `README.md` | Remove the wording about the shell, `/v1`, the registry and diagnostics |
| `tests/test_llm_contract.py` | Remove the `/v1` → `/api/llm` map test |
| `tests/test_main.py` | Remove the shell-entry checks. Keep the `/health` and token tests. |
| `tests/test_foundation.py` | Remove the registry, `/healthz`, diagnostics and shell-fallthrough tests |
| `tests/test_restored_contracts.py`, `tests/test_standalone_bootstrap.py` | Remove the `agent_trace` and registry parts |
| `contracts/openapi.json` | Regenerate |

## Test files to delete
- Possibly **`tests/test_foundation.py`**, the whole file. It tests mostly the registry. Confirm at the start of the session once the leftover tests are known.
- **Test functions** for `/v1` aliases, the shell, `/healthz`, diagnostics, `agent_trace` and the registry. They'll be listed by name at the start of the session.

## Not in this step
- The in-memory trace store and `/traces/*` (step 6).

## Verification
1. Run `.venv/bin/pytest -q` before starting, and record the result.
2. Add the new tests and confirm they fail.
3. Make the changes. Regenerate `contracts/openapi.json`. Run `.venv/bin/pytest -q`; all should pass. Show the output.
4. Run `grep -rn "SHELL_DIST\|alias_registration\|healthz\|agent_trace\|service_registry" src tests config main.py`. Expect no matches.

## Commit
```
git add -A .                                             # stage every change in gateway/
git commit -m "Shrink step 3: remove non-LLM features (v1 aliases, shell, registry)"   # save the snapshot
```
