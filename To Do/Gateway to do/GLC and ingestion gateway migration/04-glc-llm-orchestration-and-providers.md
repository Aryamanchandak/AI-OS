# Plan 04 — GLC LLM Orchestration and Providers

## Related decisions

Depends on Plan 02 §3 (dependency container) for the `LLMService` injection
point. Enforces the "no hard-wiring between GLC's own internal components"
program rule via the Provider protocol in Work Package A. Guarantees: the
mandatory metering/audit/telemetry pipeline stage (Work Package C, step 9) is
non-optional regardless of transport — this is what backs the "an LLM call is
always logged" invariant even if some other component later moves behind an
MCP-style call boundary. Ingestion (Plan 06) is the first, but not the only,
future consumer of the decisions below — treat both new decisions as
program-wide, not ingestion-specific.

## Goal

Move GLC's model gateway capabilities into `gateway.llm` without creating a
new multi-provider monolith. Preserve `/v1/chat`, batch, vision, embeddings,
profiles, routing, caching, budgets, metering, structured output, and streams.

## Proposed domain shape

```text
gateway/llm/
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

- [ ] Approve this order.
- [ ] Specify a different first provider below.

### 2. Internal caller interface

Proposed default: Gateway domains depend on a small injected `LLMService`
protocol using named profiles. External callers retain HTTP. Internal domains
do not call the Gateway's own HTTP port.

- [ ] Approve in-process typed service calls.
- [ ] Require internal HTTP isolation; explain why below.

### 3. Route naming

Proposed default: keep `/v1/*` throughout migration. Introduce `/api/llm/*`
only if it provides a real contract improvement, not merely cosmetic nesting.

- [ ] Keep `/v1/*` as the primary model contract.
- [ ] Add `/api/llm/*` aliases.
- [ ] Design a replacement contract before implementation.

### 4. Behavioral optimizations

Proposed default: first achieve behavioral equivalence. Then make separate,
tested changes for HTTP connection reuse, single-embedding cache misses,
atomic budget reservations, and SQLite event-loop isolation.

- [ ] Approve equivalence-first sequencing.
- [ ] Identify an optimization that must happen during the move.

### 5. Gateway client SDK for external callers

Today, ingestion is not the only future caller of `gateway.llm` — everything
built after this migration is expected to call Gateway for LLM work. Ingestion
happens to become an in-process caller once Plan 06 lands (using the
`LLMService` protocol from decision #2), but future projects that never join
the Gateway monorepo still need a supported way in.

Proposed default: formalize today's `glc.client.LLM` (currently kept only as
a compatibility shim per "Explicitly out of scope" below) into a real,
versioned SDK at `gateway/sdk/` — a small package with minimal dependencies
(HTTP client + pydantic models only, no FastAPI/DB/provider deps) that wraps
`/v1/*`. This is the same code path that exists today (`GatewayExtractor`'s
`ChatClient` protocol is already satisfied by it, unmodified); the change is
packaging and support commitment, not new architecture. Any future project —
in or out of this repo — imports this SDK rather than hand-rolling HTTP
calls or duplicating a client.

- [ ] Approve formalizing `gateway/sdk/` as the supported external client.
- [ ] Keep `glc.client.LLM` as an unpromoted compatibility shim only; describe
      the alternative for future external callers below.

### 6. Profile-to-model binding: pinned model versus routing tier

Profiles exist so that a caller names a stable task (e.g.
`knowledge-extraction-v1`) without knowing which model answers it — that
naming contract does not change. What can change is what a profile resolves
to underneath. Today every profile pins one exact provider+model
(`profiles.yaml`). `routing.yaml` already supports a price-ladder mechanism —
named tiers with a `strict` flag (only the tier's own curated models, never a
silent fallback to a cheaper or free one) and an `objective` dial (cost vs.
quality) — that isn't currently wired into `chat` profiles at all.

Proposed default: keep pinned models for profiles that require exact,
reproducible output (e.g. anything with regression-tested prompts/schemas).
For profiles where any model in a curated top tier is acceptable, bind the
profile to a `strict: true`, `objective: quality` routing tier (e.g. a tier
containing only frontier-grade OpenAI/Anthropic models) instead of one exact
model — this gets provider failover without ever silently dropping to a free
or local model, consistent with accepting cost for consistency rather than
chasing free tiers.

- [ ] Approve per-profile choice (pinned vs. strict quality tier), decided
      profile-by-profile during the provider migration (decision #1).
- [ ] Keep all profiles pinned to one exact model for now; revisit later.

## Work packages

### A. Define stable shared contracts

- Provider protocol and capability model.
- Normalized chat, embed, stream, usage, tool-call, and error models.
- Profile resolution and validation interface.
- Provider registry and dependency construction.

### B. Move providers vertically

For each provider:

- Configuration and credentials.
- Request/response translation.
- Structured-output and tool dialects.
- Streaming parser.
- Reasoning controls.
- Error normalization.
- Capabilities and provider-specific tests.
- Documentation and live-smoke instructions.

No provider package may decide global routing, budgets, or cross-provider
failover.

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

### D. Preserve compatibility

- Preserve chat, batch, vision, embed, provider/status, profile, cost, budget,
  cache, and capability routes.
- Preserve error envelopes and provider/model labels in results.
- Preserve SSE byte framing, cancellation, disconnects, and backpressure.
- Preserve old environment-variable aliases during the transition.

### E. Post-equivalence hardening

- Reuse lifespan-managed HTTP clients.
- Reuse the cache-lookup embedding during cache storage.
- Make budget check-and-reserve atomic and reconcile actual usage.
- Keep synchronous SQLite work off the event loop.
- Add bounded concurrency and repeatable latency/concurrency tests.

### F. Formalize the Gateway client SDK

- Package `gateway/sdk/` separately from server code, with its own minimal
  dependency set.
- Port `glc.client.LLM`'s public surface onto it without behavior changes.
- Document it as the supported way for any project outside Gateway's process
  to call `/v1/*`.
- Leave `GatewayExtractor` and other in-repo callers on the in-process
  `LLMService` path (decision #2) — the SDK is for callers outside the
  Gateway process, not a replacement for in-process injection.

## Explicitly out of scope

- Channels and voice.
- Ingestion source movement.
- Changing profile names used by ingestion.
- Removing the GLC client compatibility package (it becomes the SDK in Work
  Package F, not something deleted).

## Exit gate

- No concrete provider remains in the legacy multi-provider modules.
- No HTTP route contains the complete orchestration pipeline.
- Every preserved JSON and streaming contract passes against Gateway.
- Concurrent budget admission cannot overspend a configured ceiling.
- Provider clients are reused and closed cleanly.
- A semantic-cache miss embeds a prompt no more than once.
- The Gateway client SDK is packaged, documented, and passes the same
  preserved contract tests as direct HTTP calls.
- Every migrated profile has a recorded pinned-model-or-routing-tier decision
  (decision #6), not a default left unmade.

## Aryaman's comments

Add provider priorities, route choices, model-routing rules, budget semantics,
and required compatibility details here.

