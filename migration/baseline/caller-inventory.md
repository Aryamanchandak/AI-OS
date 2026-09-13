# Caller inventory — Plan 01 baseline capture

Captured 2026-09-14 via full-tree grep for: port 8111, `GLC_*` env vars,
`glc.*` imports, direct starts of `glc.main`, `/v1/*` routes, and
`/api/ingestion/*` routes. Raw grep output is kept at
`migration/baseline/caller-inventory-raw.txt`. Excluded from the search:
`.git`, `node_modules`, `.venv`, `__pycache__`, `.pytest_cache`, `dist`,
`Database/_trash`, `Original Code/` (already gitignored, contains stale
duplicate/archived GLC snapshots from before v5 — genuinely obsolete, not
enumerated line-by-line here), `Persistent Memory Chats Storage/`. One
false-positive class was also dropped by hand: floating-point numbers in
`AI Agent/data/state/memory.json` that happen to contain the digits "8111"
(embedding vectors, not port references).

## Classification

**Active — GLC itself** (`glc_v5/`): every internal reference to port 8111,
`GLC_*` vars, and `/v1/*` is GLC defining its own contract. Not a caller;
excluded from the table below.

**Active — ingestion → GLC** (`ingestion-pipeline/merged-ingestion/`):
confirmed active, not aspirational. `src/ingestion/runner.py` constructs
`glc.client.LLM` at `runner.py:74-90`; `src/ingestion/extraction/gateway.py`
routes all model calls through it; `GLC_PROFILE`/`GLC_PROFILES_PATH` are read
in `consumers/vector_consumer.py`, `coordinator/preflight.py`,
`vector/vector_store.py`. `tests/test_glc_contract.py` is a cross-project
contract test against a real GLC FastAPI app. This matches the git history
(`ingestion-pipeline` commits `d6f020c`…`e16152c`, "replace legacy gateway
package with glc v5 client"). **Owner: this migration (Plan 06 targets
removing the HTTP hop in favor of an in-process `LLMService`, per the
program roadmap — the dependency itself is expected to persist as an
in-process one, not disappear).**

  - One caveat found: `ingestion-pipeline/merged-ingestion/build/lib/ingestion/runner.py`
    is a duplicate of `src/ingestion/runner.py` under a `build/` directory —
    looks like a stale `setuptools`/build artifact, not source. Worth
    confirming it's gitignored before any history-aware import touches it;
    not fixed here (`merged-ingestion/` is marked protected by ingestion's
    own `CLAUDE.md`/`AGENTS.md` — no restructuring without Aryaman's
    explicit say-so).

**Active — shell → gateway** (`shell/src/api/client.ts`,
`shell/src/api/schema.d.ts`): the built React UI calls
`/api/ingestion/{run, run/start, run/decision, run/retry,
run/{run_id}/report, evidence/{run_id}/{item_id}, cleanup/mappings,
cleanup/mappings/{mapping_id}}` — an exact match to gateway's own
`openapi.json`. **Owner: this migration; also touches
`To Do/UNIFIED UI/UNIFIED_UI_PLAN.md`, which is out of scope for Plan 01 but
consumes the same compatibility freeze.**

**Active — but out of scope for this migration** (`AI Agent/src/agent/gateway.py`):
a live, running caller — `ensure_gateway()` auto-starts and calls
`http://localhost:8107/v1/providers`, `/v1/chat`, `/v1/embed`. This is
**port 8107, not 8111** — it targets the pre-GLC-v5 `llm_gateway` service
living under a separate `AI_CODE_ROOT` workspace (resolved by walking up
from `AI Agent/` to find sibling `llm_gateway`/`mcp_server` directories),
not GLC v5 at all. `AI Agent/README.md:41` and several docs under
`AI Agent/docs/AGENT OVERVIEWS/` describe the same 8107 service. This is a
real, active dependency — just not on anything this migration touches yet.
It already has its own plan: `To Do/AI Agent to do/01-agent-under-gateway-plan.md`,
which explicitly tracks migrating the agent onto `glc_v5`'s `/v1/chat` and
`/v1/embed` contracts. **No action needed from Plan 01; flagging so it isn't
mistaken for an unknown/orphaned 8111 caller — it isn't one, it's a
different, older port entirely.**

**Documentation-only** (no runtime effect): every reference inside
`To Do/Gateway to do/**/*.md` (plans 00, 02, 04, 05, 06, 07, and the source
reference `01-dismantle-glc-v5-into-gateway.md`), `To Do/AI Agent to do/01-agent-under-gateway-plan.md`,
`To Do/UNIFIED UI/UNIFIED_UI_PLAN.md`, `Project plan/SYSTEM_ARCHITECTURE.md`,
and `AI Agent/docs/**` (workflow/overview/red-team reports). These encode
plan agreements and historical system descriptions, not code paths. One is
worth surfacing on its own merits: `To Do/Gateway to do/GLC and ingestion gateway migration/06-ingestion-domain-migration.md:147`
lists "Ingestion has no `glc-v5`, `glc.client`, or port-8111 dependency" as
an **exit-gate goal for Plan 06** (the future state, once ingestion talks to
Gateway in-process) — not a claim about today. Today's actual state is the
opposite (see "Active — ingestion → GLC" above), which is expected and
consistent, not a contradiction — noted here only so it doesn't get misread
later as Plan 06 documentation already being stale.

**Obsolete**: everything under `Original Code/` (already gitignored) —
duplicate/superseded `glc_v1_whatsapp`, migration-snapshot, and
"unexpected-duplicates" trees from before GLC v5 existed.

**Unknown**: none. Every match resolved to one of the categories above.

## Exit-gate status

"Unknown callers have an owner or an explicit compatibility requirement" —
satisfied: zero callers remain in the unknown bucket.
