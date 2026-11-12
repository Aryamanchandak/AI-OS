# Plan 04 — GLC LLM Orchestration and Providers

## Related decisions

Depends on Plan 02 §3 (dependency container) for constructing and owning the
`LLMService` that Gateway's own LLM routes call. Per decision #2 this service
is *not* injected into other domains — every caller, including in-process
ones, reaches it over HTTP.

Enforces the "no hard-wiring between GLC's own internal components" program
rule via the Provider protocol in Work Package A. Guarantees: the
mandatory metering/audit/telemetry pipeline stage (Work Package C, step 9) is
non-optional regardless of transport — this is what backs the "an LLM call is
always logged" invariant even if some other component later moves behind an
MCP-style call boundary. Ingestion (Plan 06) is the first, but not the only,
future consumer of the decisions below — treat every decision here as
program-wide, not ingestion-specific. (Decision #5, the external client SDK,
is deferred; the rest stand.)

## Goal

Move GLC's model gateway capabilities into `gateway.llm` without creating a
new multi-provider monolith. Preserve the chat, batch, vision, embeddings,
profiles, routing, caching, budgets, metering, structured-output, and
streaming capabilities — behavior unchanged, relocated to `/api/llm/*` per
decision #3.

## Proposed domain shape

```text
gateway/src/gateway/llm/        # package root is gateway/src/gateway/
├── api/
├── orchestration/
├── providers/
│   ├── base.py
│   ├── registry.py
│   ├── openai/
│   ├── anthropic/
│   ├── gemini/
│   ├── ollama/
│   └── openai_compatible/
├── profiles/
├── routing/
├── cache/
└── economics/
```



## Decisions required before implementation



### 1. Provider migration order

Proposed default: OpenAI first because its behavior is currently split across
`providers.py` and `direct_providers.py`; then Anthropic, Gemini, Ollama, and
OpenAI-compatible providers.

Concretely: today all providers live in two files —
`glc_v5/glc/providers.py` (1,431 lines) and `glc_v5/glc/direct_providers.py`
(450 lines) — rather than one file or package per provider. OpenAI is called
out as first specifically because its logic is the one split *across both*
of those files (some OpenAI handling in the general `providers.py`, some in
the "direct" one), so migrating it first forces the vertical-slice pattern
(Work Package B's per-provider package: config, translation, streaming,
errors, tests, docs — all together) to be proven on the messiest case, not
the cleanest one.

- [ ] Approve this order.
- [ ] Specify a different first provider below.

**How you'll verify this landed:** after OpenAI's slice moves, `providers.py`
and `direct_providers.py` should have measurably shrunk (no more OpenAI-
specific code in either), and a new `gateway/src/gateway/llm/providers/openai/` package
exists with its own tests passing independently of the other providers.

### 2. Internal caller interface

Proposed default: Gateway domains depend on a small injected `LLMService`
protocol using named profiles. External callers retain HTTP. Internal domains
do not call the Gateway's own HTTP port.

**This decision is not about port numbers.** It is about whether a call that
never leaves the process still pays for a network round-trip. Both options
below keep an HTTP LLM surface alive for external callers; they differ only in
how *in-process* domains (ingestion, after Plan 06) reach the LLM.

Concretely: today ingestion is *external* to GLC — it calls
`glc.client.LLM.chat()` over HTTP to `http://127.0.0.1:8111` (see
`ingestion-pipeline/merged-ingestion/src/ingestion/runner.py`, which imports
`glc.client` and defaults to that URL, overridable with `GLC_BASE_URL`). The
actual method signature ingestion already depends on is the `ChatClient`
protocol in `ingestion/extraction/gateway.py` — `chat(prompt=..., messages=..., profile=..., ...) -> dict`. This decision is: once ingestion moves in-process
(Plan 06), does it keep making that same call as an HTTP round-trip to
Gateway's own port, or does Gateway hand it an in-process Python object that
satisfies the same `ChatClient` shape, so the call is a normal function call?

- **Approve in-process typed service calls**: Gateway constructs one
`LLMService` object at startup and injects it into ingestion (and any
other in-process domain) directly — no network hop, no serialization, for
calls that never leave the process. External callers (anything outside
Gateway's process) still use HTTP, since they have no other way in.
- **Require internal HTTP isolation**: even in-process domains call Gateway's
own chat route (`/api/llm/chat`, per decision #3) over loopback HTTP, the
way everything reaches GLC today. Simpler mental model (one
interface for everyone) but adds real HTTP/serialization overhead and a
self-referential network dependency for a call that's already in the same
process.

- [ ] Approve in-process typed service calls.
- [x] **Require internal HTTP isolation.**

**Decided (Aryaman), 2026-09-21 — supersedes an earlier in-process tick in
this same document:** **internal HTTP isolation.** One interface for every
caller, in-process or not. Ingestion keeps making a real HTTP request —
serialize, socket, deserialize — to Gateway's own chat route, exactly as it
reaches GLC today. The in-process option is left above as the documented
alternative, not as the plan.

Separately noted: the HTTP LLM port is **redefined, not retired** — it stops
being GLC's private 8111 and becomes a Gateway-owned, registry-resolved
address (Plan 02 §4). Under this decision that address is not merely retained
for outside callers; it is the *only* way anything reaches the LLM.

**A constraint this choice dissolves — sync vs. async.** The in-process
option carried a hidden bridge. `glc/client.py` is, by its own docstring, a
*synchronous* client (`httpx.Client`, `def chat`), and the `ChatClient`
Protocol ingestion depends on is synchronous too. Verified: there is not a
single `async def` in `ingestion/extraction/gateway.py` or
`ingestion/runner.py`, and all seven `.chat(...)` call sites across ingestion
(`parsing.py`, `coordinator/preflight.py` ×2, `text_cleanup/spelling.py`,
`sources/page_scanner/cleanup.py`, `sources/book_metadata.py`,
`extraction/gateway.py`) are plain synchronous calls, while Gateway's
pipeline is `async`. Injecting an object would have required either a
sync-facade/thread-pool bridge or converting those call sites to `async`.
**Under HTTP isolation none of that is needed** — a synchronous
`httpx.Client` talking to an async server is the normal, boring case. All
seven call sites stay exactly as they are, and Plan 06 gets materially
smaller: it repoints a URL instead of rewiring an interface.

**Cost this choice accepts, recorded honestly:** every LLM call pays JSON
serialization, a loopback socket, and deserialization, in both directions;
errors arrive as `GatewayError(status_code, detail[:500])` rather than a
Python traceback; and Gateway makes HTTP calls to itself, which under heavy
load can contend for its own connection pool and event loop. The overhead is
amortized in ingestion's hottest path — extraction is batched
(`DEFAULT_BATCH_MAX_TOKENS = 12288`, default batch size 4), so one
round-trip covers several highlights rather than one per highlight.

**What this buys:** one calling convention for everything, no second code
path to keep in sync, no interface that behaves differently depending on
where the caller happens to live — and a clean seam if any domain is ever
split into its own process, since it is already talking over the wire.

**How you'll verify this landed:** a *positive* check, not an absence.
After Plan 06, `runner.py` still constructs an HTTP-based client satisfying
`ChatClient`, pointed at **Gateway's registry-resolved LLM address**
(`config/services.yaml`) rather than the hardcoded `127.0.0.1:8111` default
in `glc/client.py`. No `LLMService` object is injected into ingestion, and
none of the seven `.chat(...)` call sites has changed signature or become
`async`. A test that starts Gateway and runs an ingestion extraction
end-to-end should show a real inbound HTTP request in Gateway's own
access/audit log for each chat call — an LLM call in the audit log with no
corresponding inbound request means something bypassed the isolation
boundary.

### 3. Route naming

**Decided (Aryaman): `/api/llm/*` becomes the primary contract.** Backward
compatibility with `/v1/*` is not a constraint worth carrying — every caller
that matters is inside this repo and will be updated to the new interface as
part of its own migration.

Today GLC's LLM-relevant routes, confirmed in `glc_v5/glc/routes/chat.py`,
include `/v1/chat`, `/v1/chat/batch`, `/v1/vision`, `/v1/embed`,
`/v1/embedders`, `/v1/providers`, `/v1/capabilities`, and `/v1/status`
(economics-adjacent ones like `/v1/budget`, `/v1/cost/by_principal`,
`/v1/cache/stats`, and `/v1/pricing` live in `routes/economics.py`) — all on
port 8111. Gateway's own convention so far is `/api/<domain>/*` (e.g.
`/api/ingestion/*`, per Plan 02). The question was whether GLC's routes
switch to that convention once they move under Gateway, or keep their
`/v1/*` names unchanged — resolved above in favour of switching.

Route mapping (paths change; request/response **shapes** do not — reshaping
the contract is still a separate, later effort, not part of this migration):

| Today | After |
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

- [ ] Keep `/v1/*` as the primary model contract.
- [x] **Make `/api/llm/*` the primary model contract; callers are updated to
  match.**
- [ ] Design a replacement *shape* (not just path) before implementation.

**Open sub-question — the transition window.** This is an ordering fact, not
a compatibility argument: Plan 04 renames the routes, but ingestion does not
repoint its client until Plan 06. In between, ingestion is still calling the
old path. (Under decision #2 ingestion calls over HTTP permanently — what
Plan 06 changes is the URL it targets, not the mechanism.) Two ways to close
that:

- **Short-lived `/v1/*` alias** (recommended): the renamed router also answers
  the old paths, and Plan 07 deletes the alias at legacy cutover. Cost is one
  alias router and one deletion.
- **Pull Plan 06 forward** so nothing ever calls the old paths. Under
  decision #2 this is a small change — repointing a base URL, not rewiring
  an interface — which makes it cheaper than it previously looked.

- [ ] Short-lived `/v1/*` alias, deleted in Plan 07.
- [ ] Pull Plan 06's ingestion cutover forward instead.

**How you'll verify this landed:** re-export Gateway's OpenAPI schema and
diff it against `migration/baseline/contracts/glc-openapi.json` (captured in
Plan 01) **through the mapping table above** — for each old→new pair, the new
path exists and its request/response schema is shape-identical to the
baseline's entry for the old path. A bare path-set diff will now show every
route as removed-and-added, so the comparison must be pairwise, not literal.
Nothing from the baseline may be missing from the right-hand column.

### 4. Behavioral optimizations

**What this decision is actually asking.** Not *whether* to fix the four
problems below — they all get fixed. Only *when*: in the same commits that
move the code, or in separate commits afterwards. If a test breaks after a
fused commit, you cannot tell whether the move broke it or the fix did.

**The four problems, worst first:**

| # | Problem | What it costs you | Severity |
| --- | --- | --- | --- |
| 1 | Budget check and spend are not atomic | Real money spent past a ceiling you configured | **Correctness bug** |
| 2 | Synchronous SQLite on the event loop | One slow write stalls every other in-flight request | **Availability bug** |
| 3 | A new HTTP client per provider call | Connection churn and added latency on every call | Performance |
| 4 | Two embeddings per cache miss | One wasted embedding call (cost + latency) per miss | Performance |

Proposed default: first achieve behavioral equivalence. Then make separate,
tested changes for atomic budget reservations, SQLite event-loop isolation,
HTTP connection reuse, and single-embedding cache misses.

Each of the four is a real, separate, pre-existing characteristic of the
current code, not a hypothetical. Same numbering as the table above; this
order is used consistently in Work Package E:

1. **Atomic budget reservations** — confirmed as two separate, unlocked steps
in two separate modules: `BudgetController.admit()`
(`glc_v5/glc/economics/budget.py`, 537 lines total) only *checks* a
projected cost against `spent_usd` computed from `Meter.spend(...)`; the
actual spend gets written later, in `Meter.record()`
(`glc_v5/glc/economics/meter.py`). Nothing holds a lock between `admit()`
returning "allowed" and `record()` writing the usage, so two concurrent
requests can both call `admit()`, both see room under the ceiling, and
both proceed — overspending it. This is the one that costs real money.
2. **SQLite event-loop isolation** — GLC's SQLite access (`db.py`,
`audit/store.py`, `economics/budget.py`) is synchronous `sqlite3`; if
called directly from an `async def` route handler, it blocks the event
loop for every other concurrent request during that call. One slow write
becomes everyone's latency.
3. **HTTP connection reuse** — confirmed in `glc_v5/glc/providers.py`: calls
like `async with httpx.AsyncClient(timeout=180) as c:` (e.g. lines 481,
620, 868, 1164) open and close a fresh client inside the call method
itself, once per request, rather than reusing one client across requests.
This is what Work Package E and Plan 03 Work Package B's "lifespan-managed
outbound HTTP clients" both refer to fixing.
4. **Single-embedding cache misses** — on a semantic-cache miss, the code
should embed the prompt once and reuse that same embedding for both the
lookup and the subsequent cache write; today it may compute it twice (see
Work Package E and Exit Gate: "a semantic-cache miss embeds a prompt no
more than once").

Proposed sequencing: get the moved code passing every preserved contract
test first, *unoptimized* — same behavior, warts included — then fix these
four in separate, individually-tested commits (Work Package E). Mixing "did
the move preserve behavior" with "did the optimization also change
behavior" in one commit makes a regression much harder to isolate.

- [ ] Approve equivalence-first sequencing.
- [ ] Identify an optimization that must happen during the move.

*(Left open — comment was a request to understand, not a decision. The
explanation above is the answer; the checkbox still needs a tick. Note that
#1 is a live money-losing bug today, so if it needs to be fixed sooner than
"after the whole move lands," that is the argument for the second box.)*

**How you'll verify this landed:** Work Package E's own tests — see that
section below — are the actual proof; this decision is really "in which
commit do those tests get satisfied," equivalence-first or fused with the
move.

### 5. Gateway client SDK for external callers — DEFERRED

Today, ingestion is not the only future caller of `gateway.llm` — everything
built after this migration is expected to call Gateway for LLM work.
Ingestion becomes Plan 06's first real consumer of the HTTP-isolation
calling convention (decision #2, reversed 2026-09-21 — every caller,
in-process or not, reaches the LLM over HTTP, never an injected object),
but future projects that never join the Gateway monorepo still need a
supported way in.

**Decided (Aryaman): deferred out of this plan.** Every caller in the
foreseeable term lives in this repo, so there is no external consumer to
support yet. Revisit when a real out-of-repo caller exists.

**Consequences of deferring, recorded here so they don't get lost:**

- Work Package F is removed from this plan's scope (see below).
- **Resolved by Plan 06 (`06-ingestion-domain-migration.md` decision #2 /
  `06a-implementation-handoff.md` §0.1): `glc_v5/glc/client.py` does *not*
  become ingestion's permanent calling path.** Ingestion is given its own
  small Gateway-owned HTTP client, under `gateway/src/gateway/ingestion/`,
  satisfying the same `ChatClient` shape and pointed at Gateway's
  registry-resolved `/api/llm/chat` — it does not keep importing
  `glc_v5/glc/client.py`. That resolves what this paragraph originally left
  open: once Plan 06 lands, `glc_v5/glc/client.py` has **zero in-repo
  importers** (confirmed: ingestion was its only in-repo consumer outside
  `glc_v5`'s own tests). The file itself is not deleted by either plan —
  Plan 07 still owns whether it's ever removed — but it is an intact,
  unused compatibility shim after Plan 06, not a load-bearing hot path.
- Because the client is *not* load-bearing after Plan 06, the earlier
  argument for revisiting decision #5 sooner doesn't apply. The deferral
  holds on its original grounds only: no out-of-repo caller exists yet.
- The SDK exit-gate item is removed from this plan's exit gate.

*Original proposal, retained for whenever this is revisited:* formalize
today's `glc.client.LLM` (currently kept only as
a compatibility shim per "Explicitly out of scope" below) into a real,
versioned SDK at `gateway/sdk/` — a small package with minimal dependencies
(HTTP client + pydantic models only, no FastAPI/DB/provider deps) that wraps
the HTTP routes (`/api/llm/*` after decision #3). This is the same code
path that exists today (`GatewayExtractor`'s
`ChatClient` protocol is already satisfied by it, unmodified); the change is
packaging and support commitment, not new architecture. Any future project —
in or out of this repo — imports this SDK rather than hand-rolling HTTP
calls or duplicating a client.

- [ ] Approve formalizing `gateway/sdk/` as the supported external client.
- [ ] Keep `glc.client.LLM` as an unpromoted compatibility shim only.
- [x] **Defer entirely — no external caller exists yet; revisit when one does.**

**Grounding:** `glc_v5/glc/client.py` is 191 lines today — small, HTTP-only,
already close to what an SDK package should be. The `ChatClient` protocol it
satisfies (`ingestion/extraction/gateway.py` lines 45–57) is the exact
interface this decision is about formalizing, not redesigning.

**How you'll verify the deferral landed:** nothing is built. The only check
is negative — no `gateway/sdk/` package appears in this migration, and
`glc_v5/glc/client.py` still exists and still imports cleanly at the end of
Plan 04. *(The original verification — `gateway/sdk/` installing standalone
with no FastAPI/DB/provider imports — is preserved above for whenever this
decision is revisited.)*

### 6. Profile-to-model binding: pinned model versus routing tier

Profiles exist so that a caller names a stable task (e.g.
`knowledge-extraction-v1`) without knowing which model answers it — that
naming contract does not change. What can change is what a profile resolves
to underneath. Today every profile pins one exact provider+model
(`profiles.yaml`). `routing.yaml` already supports a price-ladder mechanism —
named tiers with a `strict` flag (only the tier's own curated models, never a
silent fallback to a cheaper or free one) and an `objective` dial (cost vs.
quality) — that isn't currently wired into `chat` profiles at all.

*Original proposal, superseded by the decision below — retained for whenever
routing is activated:* keep pinned models for profiles that require exact,
reproducible output (e.g. anything with regression-tested prompts/schemas).
For profiles where any model in a curated top tier is acceptable, bind the
profile to a `strict: true`, `objective: quality` routing tier (e.g. a tier containing only frontier-grade OpenAI/Anthropic models) instead of one exact model — this gets provider failover without ever silently dropping to a free or local
model, consistent with accepting cost for consistency rather than chasing free
tiers.

**Decided (Aryaman): profiles stay pinned; routing stays dormant.** Every
migrated profile keeps its exact provider+model pin. The `routing.yaml`
tier mechanism is **preserved as-is, and deliberately left unwired** from
chat profiles — it gets activated later, when there is real routing
intelligence to drive the tier choice. Until then, profiles are the only
model-selection mechanism.

Practically this resolves to *no migration work*: `routing.yaml` is already
not wired into chat profiles today. The instruction is "carry it across
intact, don't connect it, don't delete it."

- [ ] Approve per-profile choice (pinned vs. strict quality tier), decided
  profile-by-profile during the provider migration (decision #1).
- [x] **Keep all profiles pinned to one exact model for now; revisit later.**

**Grounding — today's actual profiles**, from `glc_v5/glc/profiles.yaml`:
`knowledge-extraction-v1` pins `anthropic-sonnet` / `claude-sonnet-4-6`
(this is the exact profile ingestion's `extraction/gateway.py` calls —
`EXTRACTION_CHAT_PROFILE = "knowledge-extraction-v1"`);
`document-segmentation-v1` and `cover-classification-v1` pin *local* models
(`phi4-local`, `cover-vision-local`) — these are natural candidates to stay
pinned, since a routing tier could silently swap in a hosted model and
change cost/privacy characteristics unexpectedly. Meanwhile
`glc_v5/glc/routing/routing.yaml` already defines tiers like `TINY`/`LARGE`/
`HUGE` with a provider `order` and a `strict` flag — the mechanism this
decision would wire *into* profiles doesn't need to be built, only
connected.

Under the decision above this is moot for now — *every* profile stays
pinned, including `knowledge-extraction-v1`, so there is no per-profile
deliberation to run. The local-model profiles (`document-segmentation-v1`,
`cover-classification-v1`) are noted anyway as the ones that would remain
pinned even after routing is eventually activated, since a tier could
otherwise swap in a hosted model and change cost/privacy characteristics.

**How you'll verify this landed:** every entry in the migrated
`profiles.yaml` still names an exact provider+model, identical to today's
values; `routing.yaml` is present in the migrated tree with its tiers intact;
and a test asserts that resolving any chat profile never passes through the
routing-tier mechanism. (The per-profile decision table the original default
would have required is not needed — there is one uniform answer.)

## Work packages



### A. Define stable shared contracts

- Provider protocol and capability model.
- Normalized chat, embed, stream, usage, tool-call, and error models.
- Profile resolution and validation interface.
- Provider registry and dependency construction.



### B. Move providers vertically

For each provider (starting with OpenAI, per decision #1 — the one split
across today's `providers.py` and `direct_providers.py`), pull all of the
following into one `gateway/src/gateway/llm/providers/<name>/` package instead of
leaving them scattered across the two shared files:

- Configuration and credentials.
- Request/response translation.
- Structured-output and tool dialects.
- Streaming parser.
- Reasoning controls.
- Error normalization.
- Capabilities and provider-specific tests.
- Documentation and live-smoke instructions.

No provider package may decide global routing, budgets, or cross-provider
failover. *(That logic belongs to Work Package C's pipeline stages 5–7, not
inside any one provider's package — a provider package should only know how
to talk to its own API.)*

**How you'll know this work package is done, provider by provider:** that
provider's code no longer appears in `providers.py`/`direct_providers.py`
(shrinking those files with each provider moved); its own package's tests
pass in isolation; and the shared contract tests (Work Package D) still
pass end-to-end through the new package.

### C. Split the chat orchestration pipeline

Create typed stages for:

1. Request validation.
2. Profile resolution.
3. Message and image normalization.
4. Usage estimation and cache lookup.
5. Classification and candidate routing.
6. Atomic budget reservation.
7. Provider call with bounded retry/failover.
8. Structured-output validation/repair.
9. Metering, audit, and telemetry finalization.
10. Cache storage and response translation.

The HTTP route should only translate, invoke the pipeline, and translate back.

Today this whole sequence lives inline inside `glc_v5/glc/routes/chat.py`
(1,494 lines) — one file mixing HTTP concerns with all ten stages above.
This work package is what actually splits that monolith the plan's Goal
promises, turning each numbered stage into its own typed, independently
testable unit that the route calls in order. Stage 9 (metering, audit, and
telemetry finalization) is called out in this plan's "Related decisions" as
*non-optional* — it's the program-wide invariant that an LLM call is always
logged, regardless of how any component is wired.

**How you'll know Work Package C is done:** `chat.py`'s route handler body
becomes short — request-translate, call the pipeline, response-translate —
with no budget/routing/retry logic left inline; each of the ten stages has
its own unit tests; a test proves stage 9 runs even when an earlier stage
takes a retry/failover path (Work Package E's added tests, and the exit
gate's "no HTTP route contains the complete orchestration pipeline").

### D. Preserve compatibility

Per decision #3, "compatibility" here means **behavioral equivalence at
renamed paths**, not URL stability. Every capability below survives the move
unchanged in shape; only its path changes, per decision #3's mapping table.

- Preserve chat, batch, vision, embed, provider/status, profile, cost, budget,
cache, and capability routes — same request/response shapes, relocated to
`/api/llm/*`.
- Preserve error envelopes and provider/model labels in results.
- Preserve SSE byte framing, cancellation, disconnects, and backpressure.
- Preserve old environment-variable aliases during the transition.
- If the `/v1/*` alias sub-option in decision #3 is taken, the alias must
route to the identical handler — not a second implementation — and carry a
deprecation marker so Plan 07 can find and delete it.

**How you'll know this is done:** diff a fresh OpenAPI export against
`migration/baseline/contracts/glc-openapi.json` (Plan 01) **pairwise through
decision #3's mapping table** — every baseline route has a counterpart at its
new path with no unexpected shape changes, and nothing from the baseline is
unaccounted for; the SSE/streaming fixtures Plan 01 captured under Work
Package C still produce byte-identical frames (path change only, frame bytes
unchanged).

### E. Post-equivalence hardening

This is where decision #4's four named optimizations actually get built —
each bullet below maps to one of them, in order:

1. Make budget check-and-reserve atomic and reconcile actual usage. *(Turn*
`economics/budget.py`*'s check-then-reserve into one atomic operation —
e.g. a single SQL statement or an explicit lock — so two concurrent
requests can't both pass the check before either reserves.)*
2. Keep synchronous SQLite work off the event loop. *(Run* `db.py`*/*
`audit/store.py`*/*`budget.py`*'s synchronous* `sqlite3` *calls in a thread
pool via* `run_in_executor`*, or an equivalent, instead of calling them
directly from* `async def` *route/pipeline code.)*
3. Reuse lifespan-managed HTTP clients. *(Provider HTTP clients built once at
startup via Plan 03's lifespan-managed clients, not per-call.)*
4. Reuse the cache-lookup embedding during cache storage. *(One embedding
call per cache miss, not two.)*

Plus, not one of the four:

- Add bounded concurrency and repeatable latency/concurrency tests.

**How you'll know Work Package E is done:** a test that fires many
concurrent chat requests against a small budget ceiling and asserts the
total spend never exceeds it (proving the atomic reservation actually
works); a test asserting a cache miss triggers exactly one embedding call
(via a call counter on a fake embedder); a load test showing one slow
SQLite write doesn't stall unrelated concurrent requests.

### F. Formalize the Gateway client SDK — DEFERRED (decision #5)

*Not in scope for this plan. Retained below as the specification to pick up
when a genuine out-of-repo caller exists. Nothing in Plan 04's exit gate
depends on it.*

- Package `gateway/sdk/` separately from server code, with its own minimal
dependency set.
- Port `glc.client.LLM`'s public surface onto it without behavior changes.
- Document it as the supported way for any project outside Gateway's process
to call `/api/llm/*`.
- Under decision #2 (HTTP isolation) there is no in-process path to leave
callers on — `GatewayExtractor` and every other in-repo caller already
speak HTTP. If this work package is ever picked up, the SDK becomes the
single client for *all* callers, in-repo and out, rather than an
outside-only package.

**How you'll know Work Package F is done:** `gateway/sdk/` installs and
imports on its own, without pulling in `fastapi`, a database driver, or any
provider SDK as a dependency; a small standalone script that only depends on
`gateway/sdk/` (no other part of this repo on its `PYTHONPATH`) can
successfully call `/api/llm/chat` against a running Gateway.

## Explicitly out of scope

- Channels and voice.
- Ingestion source movement.
- Changing profile names used by ingestion.
- Removing the GLC client compatibility package. Per decision #5 it stays an
unpromoted compatibility shim — **not** promoted to an SDK (Work Package F
is deferred) and **not** deleted. Plan 07 must leave `glc_v5/glc/client.py`
in place during legacy cleanup until nothing imports it.
- Wiring `routing.yaml` tiers into chat profiles (decision #6) — the
mechanism is carried across intact but stays dormant.
- Redesigning request/response *shapes*. Decision #3 renames paths only.



## Exit gate

- No concrete provider remains in the legacy multi-provider modules.
- No HTTP route contains the complete orchestration pipeline.
- Every preserved JSON and streaming contract passes against Gateway at its
new `/api/llm/*` path, verified pairwise against the Plan 01 baseline via
decision #3's mapping table.
- Concurrent budget admission cannot overspend a configured ceiling.
- Provider clients are reused and closed cleanly.
- A semantic-cache miss embeds a prompt no more than once.
- Every migrated profile names an exact provider+model, and a test proves no
chat profile resolves through a routing tier (decision #6).
- `routing.yaml` is present and intact in the migrated tree, and unwired.
- `glc_v5/glc/client.py` still exists and imports cleanly — no SDK was built
and no shim was deleted (decision #5).



## Decision status after Aryaman's review

| # | Decision | Status |
| --- | --- | --- |
| 1 | Provider migration order (OpenAI first) | **Resolved by recommendation** — OpenAI first (see Plan 04a §1) |
| 2 | Internal caller interface | **Decided (reversed 2026-09-21)** — internal HTTP isolation; every caller goes over the wire |
| 3 | Route naming | **Decided** — `/api/llm/*` is primary; short-lived `/v1/*` alias, deleted in Plan 07 |
| 4 | Behavioral optimizations | **Resolved by recommendation** — equivalence-first; budget atomicity fixed first in WP E |
| 5 | Gateway client SDK | **Decided** — deferred; Work Package F out of scope |
| 6 | Profile-to-model binding | **Decided** — profiles stay pinned, routing preserved but dormant |

All six are resolved. #1, #4, and #3's alias sub-option were closed by
Claude's recommendation rather than an explicit tick — they are safe defaults,
recorded in `04a-implementation-handoff.md` §1, and overriding any of them
changes that handoff accordingly.

**Implementation handoff:** `04a-implementation-handoff.md` is the
build-ready version of this plan. This document holds the *why*; 04a holds
the steps, paths, and pass/fail tests.

Cross-plan follow-ups this review created:

- **Plan 07** — must not delete `glc_v5/glc/client.py` during legacy cleanup
(decision #5), and must delete the `/v1/*` alias if decision #3's alias
sub-option is taken.
- **Plan 06** — ingestion **keeps** its HTTP `glc.client.LLM` construction in
`runner.py` (decision #2, HTTP isolation). What changes is only the target:
Gateway's registry-resolved address and `/api/llm/chat`, not
`127.0.0.1:8111/v1/chat`. No call sites change, nothing becomes `async`,
and no `LLMService` is injected into ingestion.
- **Plan 01 baseline** — the OpenAPI contract diff is now a pairwise mapped
comparison, not a path-set equality check.