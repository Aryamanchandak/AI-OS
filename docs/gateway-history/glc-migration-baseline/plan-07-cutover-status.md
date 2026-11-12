# Plan 07 local cutover status

## Scope agreed on 2026-09-25

Gateway must build, start, and preserve its own documented contracts. External
callers can migrate later. Their actual usage is not a blocker for Gateway
readiness. The previous 14-day observation requirement was an assistant-added
assumption and has been withdrawn. Port 8111 is an optional compatibility
listener; no waiting period is required to ship Gateway.

The default process model is one Gateway on port 8000 plus explicitly enabled
workers. Port 8000 remains a deliberate stable exception to the 81xx worker
range. The optional 8111 listener forwards to Gateway and can be enabled for
external callers that have not migrated.

## Checks performed

| Check | Result |
| --- | --- |
| Gateway and ingestion suite | 892 passed, 5 skipped on 2026-09-27 (the loopback test is opt-in because it binds a socket) |
| Gateway type check | Passed across 279 source files on 2026-09-27 |
| Shell | Type generation, TypeScript build, Vite build, and 123 Vitest tests passed on 2026-09-27 |
| Optional 8111 proxy | Real loopback HTTP, SSE, and text/binary WebSocket forwarding passed on 2026-09-25 (`tests/test_legacy_listener_live.py`) |
| No-submodule bootstrap | Gateway started from a copied source snapshot with neither legacy sibling directory present (`tests/test_standalone_bootstrap.py`) |
| Real process lifecycle and data recovery | Cold start, graceful restart, SQLite backup of four files, restore, and restart after forced kill passed on 2026-09-25 (`scripts/runtime_cutover_smoke.py`) |
| OpenAPI route comparison | Baseline GLC: 43 operations; Gateway: 79. Forty baseline operations are registered at their original method/path; three are covered by React shell navigation. All six backend gaps are restored. See `plan-07-openapi-audit.md`. |

The detailed classification is in `plan-07-openapi-audit.md`. Missing API
routes now return JSON 404 instead of a misleading shell HTML 200.

## Remaining work and its actual constraint

- Live provider and ingestion end-to-end tests require the relevant external
  services and credentials. The current machine has no Gateway, Ollama, or
  Neo4j listener running; the local deterministic and process checks above do
  not exercise those integrations.
- The old submodules are still referenced by `.gitmodules`. The current parent
  working tree contains many modified and untracked migration files, including
  Gateway-owned ingestion code. A fresh clone of the current remote cannot
  contain those uncommitted changes. This is a publication/versioning issue,
  not a failure of the local Gateway bootstrap check. Pushing and tagging
  replacement commits is separate from proving that the code works locally.
- Deployment service definitions and configuration rollback are not yet
  recorded. The isolated SQLite backup/restore drill passed locally.

No 14-day usage observation or migration of external callers is required for
Gateway readiness under the user's current scope.
