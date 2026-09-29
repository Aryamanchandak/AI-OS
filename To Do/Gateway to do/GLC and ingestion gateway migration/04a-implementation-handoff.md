# Plan 04a — Implementation Handoff: GLC LLM Orchestration and Providers

**Audience:** the implementing agent (Codex).
**Rationale lives in `04-glc-llm-orchestration-and-providers.md`** — this file
carries steps, paths, and pass/fail conditions. When a step says "per decision
#N," read that section of Plan 04 rather than re-deriving the reasoning. Do not
copy rationale back into this file; two copies will diverge.

---

## 0. Hard rules — read before touching anything

1. **`glc_v5/` and `ingestion-pipeline/` are READ-ONLY sources.** Every file
   you create or edit is under `gateway/`. You will be tempted to fix things
   in place inside `glc_v5/`. Do not. That tree stays untouched until Plan 07
   deletes it. (Plan 02, "Lift-and-shift boundary.")
2. **Paths change; shapes do not.** Routes move to `/api/llm/*`. Request and
   response bodies, error envelopes, provider/model labels, and SSE frame
   bytes stay byte-identical. Reshaping the contract is explicitly a later,
   separate effort.
3. **Equivalence first.** Move the code unoptimized — bugs and warts included
   — and get every contract test passing. Only then start Work Package E, in
   separate commits. Do not fuse a fix into a move commit.
4. **Stage 9 (metering/audit/telemetry) is non-optional.** Every LLM call is
   logged, on every path, including retry and failover paths. This is a
   program-wide invariant, not a Plan 04 preference.

### Do NOT do these

- Do **not** wire `routing.yaml` tiers into chat profiles (decision #6). Carry
  the file across intact and leave it unconnected.
- Do **not** build `gateway/sdk/` (decision #5 — deferred; Work Package F is
  out of scope).
- Do **not** delete `glc_v5/glc/client.py`. It's ingestion's HTTP calling
  path until Plan 06 repoints ingestion to its own Gateway-owned client
  (see §10) — deleting it here would break ingestion before that plan runs.
  Plan 07 owns whether it's ever deleted afterward.
- Do **not** hand the `LLMService` object to any domain outside
  `gateway/src/gateway/llm/`. Other domains call `/api/llm/*` over HTTP (decision #2).
- Do **not** change any profile's provider+model pin.
- Do **not** change profile *names* — `knowledge-extraction-v1` in particular
  is called by ingestion today.

---

## 1. Decisions already made — do not relitigate

| # | Decision | Resolution |
| --- | --- | --- |
| 1 | Provider migration order | **OpenAI first**, then Anthropic, Gemini, Ollama, OpenAI-compatible |
| 2 | Internal caller interface | **Internal HTTP isolation** — every caller reaches the LLM over HTTP, including in-process domains |
| 3 | Route naming | **`/api/llm/*` is primary**, with a short-lived `/v1/*` alias deleted in Plan 07 |
| 4 | Optimization sequencing | **Equivalence-first**; Work Package E in separate commits |
| 5 | Client SDK | **Deferred** — not in scope |
| 6 | Profile binding | **All profiles stay pinned**; routing preserved, dormant |

Decisions #1, #3 (the alias sub-option), and #4 were resolved by Claude's
recommendation, not by an explicit tick from Aryaman. They are safe defaults;
if Aryaman overrides any of them, this handoff changes accordingly.

**Decision #2 was reversed on 2026-09-21** to internal HTTP isolation. What
this means for you concretely: there is **no in-process injection path to
build**. The `LLMService` is still constructed and owned by the container
(§4) because Gateway's own routes call it — but it is never handed to
another domain. Ingestion, and anything else in this repo, reaches the LLM
by making a real HTTP request to `/api/llm/chat`, the same way it reaches
GLC today.

---

## 2. Prerequisites — verified present as of 2026-09-21

Do not rebuild these. They exist:

| Thing | Path | Status |
| --- | --- | --- |
| Gateway package + lockfile | `gateway/pyproject.toml`, `gateway/uv.lock` | ✅ present |
| DI container | `gateway/src/gateway/app/dependencies.py` → `DependencyContainer` | ✅ present |
| Lifespan wiring | `gateway/src/gateway/app/lifespan.py` (builds container at line ~73) | ✅ present |
| Router registration | `gateway/src/gateway/app/router_registry.py` → `migrated_domain_registrations()` | ✅ present |
| Service registry | `gateway/config/services.yaml` (gateway 8000, glc_legacy 8111) | ✅ present |
| Lifespan HTTP client | `gateway/src/gateway/platform/networking/` → `OutboundHTTPClient` | ✅ present |
| Contract baseline | `migration/baseline/contracts/glc-openapi.json` (68,668 bytes) | ✅ present |
| Gateway baseline | `migration/baseline/contracts/gateway-openapi.json` (58,608 bytes) | ✅ present |

Plan 03's output is also already in the tree (`gateway/src/gateway/audit/`,
`security/`, `policy/`, `control/`) — reuse `AuditStore` rather than porting
GLC's audit store a second time.

---

## 3. Source map — what you are moving, and how big it is

Read-only sources. Sizes tell you how much there is to cover — they are
**not** expected to shrink. Nothing in these files is edited or deleted by
this plan; you read them and author equivalents under `gateway/`.

| Source file | Lines | Moves to |
| --- | --- | --- |
| `glc_v5/glc/providers.py` | 1,431 | **read from**; reimplemented across `gateway/src/gateway/llm/providers/<name>/` |
| `glc_v5/glc/direct_providers.py` | 450 | **read from**; reimplemented across `gateway/src/gateway/llm/providers/<name>/` |
| `glc_v5/glc/routes/chat.py` | 1,494 | `gateway/src/gateway/llm/api/` (thin) + `gateway/src/gateway/llm/orchestration/` (10 stages) |
| `glc_v5/glc/routes/economics.py` | — | `gateway/src/gateway/llm/api/` + `gateway/src/gateway/llm/economics/` |
| `glc_v5/glc/economics/budget.py` | 537 | `gateway/src/gateway/llm/economics/budget.py` |
| `glc_v5/glc/economics/meter.py` | — | `gateway/src/gateway/llm/economics/meter.py` |
| `glc_v5/glc/profiles.yaml` | — | `gateway/config/profiles.yaml` — operator-editable config belongs beside `services.yaml`/`gateway.yaml`; pins unchanged |
| `glc_v5/glc/routing/routing.yaml` | — | `gateway/config/routing.yaml` — carried across intact, **unwired** |
| `glc_v5/glc/client.py` | 191 | **stays where it is, unchanged** — ingestion's HTTP calling path until Plan 06 gives ingestion its own client (§10); not deleted by this plan either way |

### Target shape

```text
gateway/src/gateway/llm/
├── api/              # HTTP routes only: translate in, call pipeline, translate out
├── orchestration/    # the 10 pipeline stages
├── providers/
│   ├── base.py       # Provider protocol + capability model
│   ├── registry.py
│   ├── openai/       # first
│   ├── anthropic/
│   ├── gemini/
│   ├── ollama/
│   └── openai_compatible/
├── profiles/
├── routing/          # carried across, dormant
├── cache/
└── economics/
```

---

## 4. Work Package A — shared contracts

Build first; everything else depends on it.

- `providers/base.py`: Provider protocol + capability model.
- Normalized models: chat, embed, stream, usage, tool-call, error.
- Profile resolution and validation interface.
- `providers/registry.py` + dependency construction.

**Wire into the existing container.** The `LLMService` is what Gateway's own
`/api/llm/*` route handlers call — it is **not** injected into ingestion or
any other domain (decision #2: HTTP isolation). In
`gateway/src/gateway/app/dependencies.py`, add an `llm: LLMService` field to
the frozen `DependencyContainer` dataclass, and a typed accessor beside
`get_service_registry` / `get_control_service`:

```python
def get_llm_service(
    container: Annotated[DependencyContainer, Depends(get_container)],
) -> LLMService:
    return container.llm
```

Construct it in `lifespan.py`'s existing `DependencyContainer(...)` call.
`DependencyContainer.close()` already exists and already awaits
`self.http.close()` — provider clients you open at startup close there too,
in reverse construction order.

**Done when:** the container constructs with an `LLMService` and the app still
starts; the only consumers of `get_llm_service` are Gateway's own
`/api/llm/*` route handlers; no domain logic has leaked into `app/` or
`platform/`.

---

## 5. Work Package B — move providers vertically, OpenAI first

OpenAI is first because its logic is the one split *across both*
`providers.py` and `direct_providers.py` — it proves the pattern on the
messiest case (decision #1).

For each provider, pull all of this into one `providers/<name>/` package:

- Configuration and credentials
- Request/response translation
- Structured-output and tool dialects
- Streaming parser
- Reasoning controls
- Error normalization
- Capabilities and provider-specific tests
- Documentation and live-smoke instructions

**No provider package may decide global routing, budgets, or cross-provider
failover.** That is Work Package C, stages 5–7. A provider package knows only
how to talk to its own API.

**Done when, per provider:** every code path for that provider in
`providers.py` and `direct_providers.py` has a counterpart under
`gateway/src/gateway/llm/providers/<name>/` — track this as an explicit checklist per
provider, since the source files are read-only and will **not** shrink as
evidence; the new package's tests pass in isolation; and Work Package D's
contract tests pass end-to-end through it.

---

## 6. Work Package C — split the orchestration pipeline

`routes/chat.py` is 1,494 lines mixing HTTP concerns with all ten stages.
Split into typed, independently testable stages:

1. Request validation
2. Profile resolution
3. Message and image normalization
4. Usage estimation and cache lookup
5. Classification and candidate routing
6. Atomic budget reservation
7. Provider call with bounded retry/failover
8. Structured-output validation/repair
9. **Metering, audit, and telemetry finalization** — non-optional, all paths
10. Cache storage and response translation

The HTTP route translates in, invokes the pipeline, translates out. Nothing
else.

**Done when:** the route handler body is short with no budget/routing/retry
logic inline; each stage has unit tests; **a test proves stage 9 runs even
when an earlier stage takes a retry or failover path.**

---

## 7. Work Package D — compatibility at new paths

Register the router via the existing pattern — add an `llm` entry to
`migrated_domain_registrations()` in `router_registry.py`, following
`gateway.control.routes.registration()`, with `prefix="/api/llm"`.

### Route mapping (decision #3)

| Today (GLC, port 8111) | After (Gateway) |
| --- | --- |
| `/v1/chat` | `/api/llm/chat` |
| `/v1/chat/batch` | `/api/llm/chat/batch` |
| `/v1/vision` | `/api/llm/vision` |
| `/v1/embed` | `/api/llm/embed` |
| `/v1/embedders` | `/api/llm/embedders` |
| `/v1/providers` | `/api/llm/providers` |
| `/v1/capabilities` | `/api/llm/capabilities` |
| `/v1/status` | `/api/llm/status` |
| `/v1/budget` | `/api/llm/budget` |
| `/v1/cost/by_principal` | `/api/llm/cost/by_principal` |
| `/v1/cache/stats` | `/api/llm/cache/stats` |
| `/v1/pricing` | `/api/llm/pricing` |

Also preserve: error envelopes, provider/model labels in results, SSE byte
framing, cancellation, disconnects, backpressure, and old environment-variable
aliases.

### The `/v1/*` alias

Ingestion calls over HTTP permanently (decision #2); what Plan 06 changes is
only the base URL it targets. Until that repoint happens, ingestion is still
calling the old paths — the alias covers that window.

Register the alias so that it **routes to the identical handler** — not a
second implementation — and mark it deprecated so Plan 07 can find and delete
it.

*Note for whoever schedules this:* because decision #2 made Plan 06's client
change a one-line base-URL repoint rather than an interface rewrite, "do the
repoint first and skip the alias entirely" is now a cheap alternative. That
is a scheduling call for Aryaman, not yours — build the alias unless told
otherwise.

**Done when:** export Gateway's OpenAPI and compare **pairwise** against
`migration/baseline/contracts/glc-openapi.json` using the table above — for
each old→new pair, the new path exists and its schema is shape-identical to
the baseline's entry for the old path, and nothing in the baseline is
unaccounted for. A bare path-set diff will show every route as
removed-and-added; the comparison must be pairwise. Plan 01's SSE/streaming
fixtures still produce byte-identical frames.

---

## 8. Work Package E — post-equivalence hardening

Separate commits, each individually tested, in this order (worst first).
**All paths below refer to the *migrated* copies under
`gateway/src/gateway/llm/`**, not the read-only originals in `glc_v5/` —
Work Package E runs after the move, so there is nothing to fix in the
legacy tree.

1. **Make budget check-and-reserve atomic.** `economics/budget.py`'s
   `BudgetController.admit()` only *checks* projected cost against
   `spent_usd`; the spend is written later by `Meter.record()` in
   `economics/meter.py`. Nothing holds a lock in between, so two concurrent
   requests both pass and both spend. Collapse into one atomic operation —
   single SQL statement or an explicit lock — and reconcile actual usage.
   *This is a live money-losing bug; it is first for that reason.*
2. **Keep synchronous SQLite off the event loop.** `db.py`, `audit/store.py`,
   `economics/budget.py` use synchronous `sqlite3`. Run via `run_in_executor`
   or equivalent instead of calling directly from `async def` code.
3. **Reuse lifespan-managed HTTP clients.** `providers.py` opens
   `async with httpx.AsyncClient(timeout=180) as c:` per call (see lines 481,
   620, 868, 1164). Build once at startup via the existing
   `OutboundHTTPClient` / container pattern; close in `close()`.
4. **Reuse the cache-lookup embedding during cache storage.** One embedding
   call per cache miss, not two.

Plus: bounded concurrency and repeatable latency/concurrency tests.

**Done when:** a test fires many concurrent chat requests against a small
budget ceiling and asserts total spend never exceeds it; a test asserts a
cache miss triggers exactly one embedding call (call counter on a fake
embedder); a load test shows one slow SQLite write does not stall unrelated
concurrent requests.

---

## 9. Exit gate — all must pass

- [ ] Every provider has its own package under
      `gateway/src/gateway/llm/providers/<name>/`, and no provider logic
      lives in shared files inside `gateway/`. (The legacy `providers.py` /
      `direct_providers.py` still contain their code — they are read-only
      sources and are **not** expected to shrink; Plan 07 deletes them.)
- [ ] No HTTP route contains the complete orchestration pipeline.
- [ ] Every preserved JSON and streaming contract passes at its new
      `/api/llm/*` path, verified pairwise against the Plan 01 baseline.
- [ ] Concurrent budget admission cannot overspend a configured ceiling.
- [ ] Provider clients are reused and closed cleanly.
- [ ] A semantic-cache miss embeds a prompt no more than once.
- [ ] Every migrated profile names an exact provider+model, unchanged from
      today, and a test proves no chat profile resolves through a routing tier.
- [ ] `routing.yaml` is present and intact in the migrated tree, and unwired.
- [ ] `glc_v5/glc/client.py` still exists and imports cleanly — no SDK built,
      nothing deleted by this plan. It remains ingestion's calling path
      until Plan 06 gives ingestion its own client (§10) — not a permanent
      arrangement, just not this plan's change to make.
- [ ] No domain outside `gateway/src/gateway/llm/` imports `LLMService` or calls
      `get_llm_service` — every other caller goes over HTTP (decision #2).
- [ ] `glc_v5/` is untouched: `git -C glc_v5 status --porcelain` prints
      nothing, and the `glc_v5` submodule pointer in the root repo is
      unchanged from where this plan started.

---

## 10. Downstream constraints — context, not work for this plan

- **Plan 06 (ingestion):** **Correction — resolved differently than this
  section originally said.** Ingestion does not keep importing
  `glc_v5/glc/client.py`; it gets its own small Gateway-owned HTTP client
  under `gateway/src/gateway/ingestion/`, satisfying the same `ChatClient`
  shape, pointed at Gateway's registry-resolved address and `/api/llm/chat`
  instead of `127.0.0.1:8111/v1/chat` (`06-ingestion-domain-migration.md`
  decision #2, `06a-implementation-handoff.md` §0.1). What's still true from
  the original text: no call sites become `async`, no object is injected,
  and the sync/async bridge the in-process option would have required still
  does not apply — a synchronous `httpx`-based client against an async
  server is the normal case either way. **Not Plan 04's job either way** —
  this note stays here only as context for whoever reads Plan 04 next.
- **Plan 07 (cutover):** deletes the `/v1/*` alias; must **not** delete
  `glc_v5/glc/client.py` at all while decision #2 stands — under HTTP
  isolation it is the permanent calling path for every in-repo consumer, not
  a shim awaiting removal; decides whether ports 8000/8111 move into the
  reserved `81xx` range.
- **Plan 01 baseline:** the contract check is now a pairwise mapped
  comparison, not path-set equality.
