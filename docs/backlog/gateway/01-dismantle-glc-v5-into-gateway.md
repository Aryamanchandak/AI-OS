# Dismantle GLC v5 and Rebuild It Inside the AI OS Gateway

This document describes a structural migration, not a simple folder move.
The goal is to take `glc_v5` apart by responsibility, preserve its working
behaviour, and rebuild those responsibilities as first-class modules of the
AI OS gateway.

Do not begin by copying files or changing imports. Complete the baseline and
foundation phases first so each later move can be verified independently.

## Decision

`glc_v5` should not remain a permanent standalone architectural unit under
`gateway/services/glc_v5`.

Instead:

- The AI OS gateway becomes the owning application and repository boundary.
- GLC's LLM, channel, voice, security, audit, control, routing, cache,
  economics, and telemetry capabilities become gateway domains.
- Provider- and channel-specific implementation is organized vertically:
  everything specific to OpenAI belongs under `providers/openai/`, everything
  specific to Telegram belongs under `channels/providers/telegram/`, and so
  on.
- Truly shared contracts remain in small, explicit shared modules.
- The current `/v1/*` interface remains available through a compatibility
  layer until every caller has migrated.
- `glc_v5` is removed only after the rebuilt gateway passes the original
  contracts and all callers use the new ownership boundary.

## Why this work is needed

GLC has strong runtime concepts but an uneven internal structure.

Good existing examples:

- `glc/channels/catalogue/<channel>/` usually colocates adapter code,
  schemas, tests, setup material, and documentation.
- `glc/voice/stt/providers/<provider>/` and
  `glc/voice/tts/providers/<provider>/` are already close to the desired
  provider-owned structure.
- Budget admission, provider failover, audit records, trust classification,
  telemetry, and semantic caching are real, tested gateway responsibilities.

Current structural problems:

- `glc/providers.py` is a roughly 1,400-line multi-provider module.
- OpenAI and Anthropic logic is split between `providers.py` and
  `direct_providers.py`.
- `glc/routes/chat.py` is a roughly 1,500-line pipeline containing HTTP
  routing, profile resolution, image handling, caching, classification,
  provider selection, budget admission, retries, failover, structured output,
  telemetry, metering, batching, vision, and embeddings.
- Configuration is spread across root YAML files, environment handling, and
  provider construction code.
- Port `8111` appears throughout implementation, scripts, examples, service
  templates, and documentation instead of being resolved from one gateway
  service registry.
- The root AI OS repository currently tracks `glc_v5` as a Git submodule,
  while `gateway/` is currently untracked. This must be resolved deliberately
  so source history and working changes are not lost.

## Design principles

1. The gateway owns orchestration; integrations own integration-specific
   behaviour.
2. Everything specific to one provider or channel lives in that provider or
   channel folder.
3. Shared contracts are centralized only when two or more implementations
   genuinely share them.
4. Provider credentials stay inside provider infrastructure and are never
   exposed to channel, UI, or agent modules.
5. HTTP routes translate requests and responses; they do not contain the
   orchestration pipeline.
6. Domain services do not obtain dependencies from module-level globals.
7. Ports and service URLs have one source of truth, with environment variables
   available as deployment overrides.
8. Every migration step preserves externally observable behaviour.
9. Old compatibility interfaces are deleted only after their callers have
   moved.
10. A passing test suite is required after every migration slice.
11. Do not mix structural movement with behavioural optimization unless the
   optimization has its own tests and commit.
12. The final gateway may run capabilities in one process or several
   processes, but process boundaries must follow operational needs rather than
   old repository boundaries.

## Target repository structure

```text
gateway/
├── pyproject.toml
├── uv.lock
├── README.md
├── config/
│   ├── gateway.yaml
│   ├── services.yaml
│   └── logging.yaml
├── src/gateway/
│   ├── app/
│   │   ├── main.py
│   │   ├── lifespan.py
│   │   ├── middleware.py
│   │   └── dependencies.py
│   │
│   ├── platform/
│   │   ├── configuration/
│   │   ├── database/
│   │   ├── networking/
│   │   ├── observability/
│   │   └── service_registry/
│   │
│   ├── llm/
│   │   ├── api/
│   │   │   ├── routes.py
│   │   │   └── schemas.py
│   │   ├── orchestration/
│   │   │   ├── pipeline.py
│   │   │   ├── retry.py
│   │   │   ├── failover.py
│   │   │   ├── structured_output.py
│   │   │   └── image_inputs.py
│   │   ├── providers/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── openai/
│   │   │   │   ├── client.py
│   │   │   │   ├── config.py
│   │   │   │   ├── schemas.py
│   │   │   │   ├── translation.py
│   │   │   │   ├── capabilities.py
│   │   │   │   ├── README.md
│   │   │   │   └── tests/
│   │   │   ├── anthropic/
│   │   │   ├── gemini/
│   │   │   ├── ollama/
│   │   │   └── openai_compatible/
│   │   ├── routing/
│   │   ├── profiles/
│   │   ├── cache/
│   │   └── economics/
│   │
│   ├── channels/
│   │   ├── core/
│   │   │   ├── contracts.py
│   │   │   ├── registry.py
│   │   │   ├── pairing.py
│   │   │   └── service.py
│   │   └── providers/
│   │       ├── telegram/
│   │       ├── whatsapp/
│   │       ├── gmail/
│   │       ├── slack/
│   │       ├── discord/
│   │       └── ...
│   │
│   ├── voice/
│   │   ├── stt/
│   │   │   ├── core/
│   │   │   └── providers/
│   │   └── tts/
│   │       ├── core/
│   │       └── providers/
│   │
│   ├── security/
│   │   ├── policies/
│   │   ├── pairing/
│   │   ├── rate_limits/
│   │   └── ssrf/
│   ├── audit/
│   └── control/
├── static/
├── scripts/
└── tests/
    ├── contracts/
    ├── integration/
    └── performance/
```

Tests specific to one provider or channel should live beside that feature.
Cross-domain contract and integration tests should remain under the root
`tests/` folder.

## Ownership boundaries inside the new structure

### Gateway application

Owns:

- FastAPI application construction.
- Shared authentication middleware.
- Application lifespan and dependency construction.
- Route mounting.
- Service registry and port resolution.
- UI shell and static asset delivery.
- Cross-domain health and readiness reporting.

Must not own:

- Vendor request translation.
- Provider retry quirks.
- Telegram, Gmail, Slack, or other channel wire formats.
- LLM routing decisions.
- Database queries belonging to a specific domain.

### LLM orchestration

Owns the ordered request pipeline:

```text
validate request
    -> resolve profile
    -> normalize messages and images
    -> estimate usage
    -> check semantic cache
    -> classify and route
    -> reserve budget
    -> call provider with bounded retry/failover
    -> validate structured output
    -> meter and audit
    -> store cache result
    -> return response
```

Each step should have a typed input/output boundary. The HTTP route should call
this pipeline rather than implement it.

### Provider folders

Each provider folder owns:

- Authentication and environment configuration.
- Vendor endpoints.
- Request and response schemas.
- Message and tool translation.
- Reasoning and structured-output dialects.
- Streaming parsing.
- Vendor-specific error normalization.
- Provider capabilities.
- Provider-specific tests and setup documentation.

The provider folder must not decide global routing, budgets, tenant policy, or
cross-provider failover.

### Channel folders

Each channel folder owns:

- Native webhook or polling format.
- Signature verification specific to that channel.
- Native-to-canonical envelope translation.
- Canonical reply-to-native translation.
- Provider API client or injected transport.
- Setup instructions, schemas, tests, and optional development harnesses.

Pairing policy, trust classification, generic rate limiting, and the canonical
channel envelope remain shared channel/security capabilities.

## Current-to-target mapping

| Current GLC location | Target gateway location |
|---|---|
| `glc/main.py` | `app/main.py` and `app/lifespan.py` |
| `glc/routes/chat.py` | `llm/api/routes.py` and `llm/orchestration/*` |
| `glc/llm_schemas.py` | `llm/api/schemas.py` plus provider-local schemas |
| `glc/providers.py` | `llm/providers/base.py`, provider folders, and registry |
| `glc/direct_providers.py` | `llm/providers/openai/` and `anthropic/` |
| `glc/embedders.py` | `llm/providers/*/embeddings.py` or `llm/cache/embedding_service.py` |
| `glc/profiles.py`, `profiles.yaml` | `llm/profiles/` |
| `glc/routing/` | `llm/routing/` |
| `glc/cache/` | `llm/cache/` |
| `glc/economics/` | `llm/economics/` |
| `glc/channels/envelope.py` | `channels/core/contracts.py` |
| `glc/channels/registry.py` | `channels/core/registry.py` |
| `glc/channels/catalogue/*` | `channels/providers/*` |
| `glc/voice/*` | `voice/*` |
| `glc/security/*` | `security/*` |
| `glc/audit/*` | `audit/*` |
| `glc/routes/control.py` | `control/api.py` |
| `glc/telemetry/*` | `platform/observability/` |
| `glc/db.py` | domain repositories plus shared database primitives |
| `static/*` | gateway `static/` or the React shell, by page |
| `daemon/*` | gateway deployment/runtime scripts |

`glc/db.py` must be split by data ownership rather than moved intact. Audit,
metering, semantic cache, budgets, pairing, and channel state should each own
their repository or store implementation. Connection setup, migrations, and
transaction helpers may remain shared.

## Runtime and port model

The final repository can contain both in-process domains and separately
launched services.

```text
AI OS Gateway :8000
       |
       +-- LLM API, routing, cache, budgets
       +-- channels and channel administration
       +-- voice API
       +-- ingestion API
       +-- control, audit, and observability APIs

External or isolated processes
       +-- S16 agent runtime :8113
       +-- provider/channel workers when required
       +-- telemetry collector :4318
       +-- tracing UI :16686
```

Most former GLC HTTP routes can run directly in the main gateway on port 8000.
A separate process should exist only when it provides meaningful isolation,
independent scaling, or a required long-running worker lifecycle.

### Central service registry

`gateway/config/services.yaml` becomes the source of truth:

```yaml
gateway:
  host: 127.0.0.1
  port: 8000

services:
  s16:
    host: 127.0.0.1
    port: 8113
    health_path: /health

  telemetry:
    host: 127.0.0.1
    port: 4318

  tracing_ui:
    host: 127.0.0.1
    port: 16686

  telegram_worker:
    enabled: false
    host: 127.0.0.1
    port: 8210
```

Rules:

- Reject duplicate enabled ports at startup.
- Validate port ranges and host values.
- Derive internal base URLs from the registry.
- Allow environment overrides for deployment.
- Report resolved services through an authenticated diagnostic endpoint.
- Keep secrets out of `services.yaml`.
- Update documentation and service templates from the same resolved settings
  rather than copying port numbers manually.

## Compatibility strategy

Do not force every existing caller to change during the structural migration.

```text
existing /v1/chat request
        |
        v
temporary compatibility route
        |
        v
gateway.llm.orchestration.ChatPipeline
        |
        v
provider implementation
```

Compatibility requirements:

- Preserve `/v1/chat`, `/v1/chat/batch`, `/v1/vision`, `/v1/embed`,
  `/v1/transcribe`, `/v1/speak`, channel, budget, cost, and status contracts.
- Preserve status codes and error envelope shapes.
- Preserve streaming SSE framing and WebSocket behaviour.
- Preserve profile pinning, provider names, routing shortcuts, and defaults.
- Preserve existing environment variables until callers and deployment
  templates have migrated.
- Maintain an OpenAPI snapshot and explicitly approve intentional changes.
- Add new `/api/llm/*`, `/api/channels/*`, and `/api/voice/*` naming only if it
  materially improves the unified gateway API.
- Remove compatibility endpoints only after a caller inventory shows no
  remaining users.

## Efficiency improvements to make after structural seams exist

These are real improvements, but each should be separate from pure file moves.

### 1. Reuse the semantic-cache embedding

On a semantic-cache miss, the request prompt is embedded during lookup and
then embedded again during storage. Return the computed vector as part of the
lookup result and pass it into `store()`.

Expected result: one embedding request per cache miss instead of two.

### 2. Reuse provider HTTP clients

Construct shared `httpx.AsyncClient` instances during gateway lifespan and
close them during shutdown. Inject the appropriate client into each provider.

Expected result: connection pooling, fewer TCP/TLS handshakes, and predictable
connection limits.

### 3. Keep SQLite off the event loop

Choose one of:

- A dedicated database worker with a bounded queue.
- An async SQLite adapter.
- Explicit `asyncio.to_thread` boundaries for synchronous store operations.

Preserve transactional semantics and test concurrent calls.

### 4. Reserve budgets atomically

Budget admission must reserve projected spend in the same transaction that
checks remaining capacity. Reconcile the reservation against actual usage when
the provider finishes or release it when the request fails.

Expected result: concurrent requests cannot collectively pass the same budget
ceiling.

### 5. Bound or replace linear semantic search

The existing 5,000-entry cap is acceptable for local operation. Before raising
that cap, introduce a measured index strategy rather than allowing an
unbounded Python cosine scan.

### 6. Add repeatable performance tests

Measure at least:

- Cached and uncached chat latency.
- Concurrent local-model requests.
- Ledger-write latency under concurrency.
- Semantic-cache lookup time at 100, 1,000, and 5,000 entries.
- Provider connection reuse.
- Budget admission under concurrent requests.

## Migration plan

### Phase 0: Protect the current state

- [ ] Finish and review the current ownership-cleanup diff in `glc_v5`.
- [ ] Run the complete GLC test suite.
- [ ] Run lint and type checks.
- [ ] Commit and push the GLC changes.
- [ ] Record the exact GLC commit referenced by the AI OS repository.
- [ ] Commit the existing `gateway/` project so it is no longer untracked.
- [ ] Export and commit a baseline GLC OpenAPI document.
- [ ] Capture representative JSON, streaming, WebSocket, budget-refusal, and
      provider-failure fixtures.
- [ ] Produce a caller inventory for GLC URLs and environment variables.

Exit condition: both repositories are clean, recoverable, and reproducible;
the current behaviour can be tested without referring to memory or ad hoc
manual steps.

### Phase 1: Create the gateway foundation

- [ ] Add a gateway `pyproject.toml` and lockfile.
- [ ] Move `gateway/main.py` into `src/gateway/app/main.py`.
- [ ] Extract authentication middleware.
- [ ] Extract application lifespan management.
- [ ] Create typed dependency containers instead of adding more app-state
      globals.
- [ ] Create `config/services.yaml` and typed service-registry loading.
- [ ] Add duplicate-port and malformed-service validation.
- [ ] Preserve the existing ingestion API and shell behaviour.

Exit condition: the current gateway works from the new package layout and all
existing gateway tests pass.

### Phase 2: Import GLC history into the gateway repository

Because `glc_v5` is currently a submodule, do not copy its files using Finder
or an ordinary recursive copy.

- [ ] Decide whether full GLC history or a single migration snapshot should be
      preserved in the AI OS repository.
- [ ] Prefer a history-preserving subtree or repository-history import.
- [ ] Import GLC temporarily under a clearly marked migration prefix.
- [ ] Verify that `git log --follow` can trace important files.
- [ ] Keep the original submodule until the imported code has passed its
      baseline contracts.
- [ ] Do not delete `.gitmodules` or the original submodule entry yet.

Exit condition: GLC source exists inside the gateway repository with the
chosen history policy documented, while the original remains recoverable.

### Phase 3: Move shared platform infrastructure

- [ ] Create gateway configuration primitives.
- [ ] Create database connection and migration primitives.
- [ ] Move telemetry initialization to `platform/observability/`.
- [ ] Move shared outbound HTTP client construction to
      `platform/networking/`.
- [ ] Build the gateway health/readiness aggregation interface.
- [ ] Preserve GLC's existing startup failure reporting.

Exit condition: shared infrastructure can be constructed and shut down by the
gateway lifespan without importing the old `glc.main` application.

### Phase 4: Move security, audit, and control

- [ ] Move pairing and trust classification.
- [ ] Move allowlists, rate limits, and SSRF protection.
- [ ] Move policy schemas and evaluation.
- [ ] Move audit records and queries.
- [ ] Move control endpoints.
- [ ] Add contract tests proving identical authorization and status codes.

Exit condition: these domains run through the gateway application while old
GLC routes can delegate to them during transition.

### Phase 5: Rebuild LLM providers vertically

Move one provider at a time. OpenAI should be the first slice because its
implementation is currently divided across multiple files.

- [ ] Define the shared provider protocol and normalized result/error models.
- [ ] Create the provider registry.
- [ ] Move OpenAI request, response, streaming, tool, reasoning, and structured
      output behaviour into `providers/openai/`.
- [ ] Move OpenAI-specific tests beside the provider.
- [ ] Repeat for Anthropic.
- [ ] Repeat for Gemini.
- [ ] Repeat for Ollama.
- [ ] Extract the genuinely shared OpenAI-compatible transport.
- [ ] Move Groq, Cerebras, NVIDIA, GitHub Models, and OpenRouter configuration
      into explicit provider packages or thin configurations over the shared
      transport.
- [ ] Reuse lifespan-managed HTTP clients.

Exit condition: no concrete provider implementation remains in the old
`providers.py` or `direct_providers.py` modules.

### Phase 6: Break apart the chat pipeline

- [ ] Move request/response schemas into `llm/api/`.
- [ ] Extract profile resolution.
- [ ] Extract message and image normalization.
- [ ] Extract cache admission and storage.
- [ ] Extract routing and candidate selection.
- [ ] Extract budget reservation.
- [ ] Extract bounded retry and failover.
- [ ] Extract structured-output validation and repair.
- [ ] Extract metering, audit, and telemetry finalization.
- [ ] Create a `ChatPipeline` service with injected dependencies.
- [ ] Reduce the HTTP route to validation, pipeline invocation, and response
      translation.
- [ ] Preserve SSE streaming behaviour with dedicated streaming tests.

Exit condition: no single chat orchestration file combines all pipeline
stages, and the old API contracts remain green.

### Phase 7: Move channels and voice

- [ ] Create shared channel contracts and registry.
- [ ] Move one channel folder at a time without flattening its internal files.
- [ ] Keep channel-specific setup, schemas, tests, and transports together.
- [ ] Move channel administration and bridge routes.
- [ ] Create shared STT and TTS contracts.
- [ ] Move voice providers one at a time.
- [ ] Verify long-running polling, WebSocket, webhook, and shutdown behaviour.

Exit condition: no runtime channel or voice implementation imports the old
`glc` package.

### Phase 8: Consolidate ports and routes

- [ ] Make the gateway service registry authoritative for process ports.
- [ ] Run migrated HTTP capabilities on gateway port 8000 where isolation is
      not required.
- [ ] Generate internal service URLs from resolved registry entries.
- [ ] Update daemon, launchd, systemd, Windows, Docker, demo, and documentation
      references.
- [ ] Keep a temporary listener or proxy on 8111 only if a caller still needs
      it.
- [ ] Test HTTP streaming and WebSocket proxying before routing either through
      a compatibility listener.
- [ ] Add diagnostics showing resolved ports and service health without
      exposing secrets.

Exit condition: port changes happen in one configuration source, duplicate
ports fail startup, and no production code relies on a copied literal `8111`.

### Phase 9: Remove the old GLC boundary

- [ ] Confirm the imported gateway modules pass every preserved GLC contract.
- [ ] Confirm S16 and all other callers use supported gateway URLs.
- [ ] Confirm no runtime import references `glc.*`.
- [ ] Confirm no deployment script starts `glc.main`.
- [ ] Remove the compatibility listener when the caller inventory is empty.
- [ ] Remove the original `glc_v5` submodule from the parent repository.
- [ ] Update `.gitmodules` deliberately.
- [ ] Archive or mark the standalone GLC repository read-only only after the
      gateway commit is pushed and recoverable.
- [ ] Replace old GLC documentation with gateway-domain documentation.

Exit condition: `glc_v5` is no longer required to build, run, test, or operate
AI OS.

## Recommended first vertical slice: OpenAI

Use OpenAI to prove the desired organization before migrating every provider.

The slice is complete when this folder contains everything needed to
understand and test OpenAI-specific behaviour:

```text
llm/providers/openai/
├── __init__.py
├── client.py
├── config.py
├── schemas.py
├── translation.py
├── capabilities.py
├── README.md
└── tests/
    ├── test_chat.py
    ├── test_streaming.py
    ├── test_tools.py
    ├── test_reasoning.py
    ├── test_structured_output.py
    └── test_errors.py
```

The folder may import only stable shared contracts and platform clients. It
must not reach back into a legacy multi-provider module for half of its
behaviour.

## Risks and controls

### Risk: rewriting and moving simultaneously

Control: move behind a compatibility interface first; optimize in a later
commit with focused tests.

### Risk: losing Git history

Control: use a documented subtree/history-import strategy and verify file
history before removing the submodule.

### Risk: one process gains every secret

Control: inject only provider-specific configuration into each provider. Keep
the option to run sensitive or failure-prone workers in separate processes.

### Risk: hidden callers depend on port 8111

Control: inventory references, instrument compatibility traffic, and keep a
temporary listener until usage reaches zero.

### Risk: WebSocket or SSE behaviour changes

Control: preserve byte-level fixtures and add tests for framing, disconnects,
backpressure, and shutdown.

### Risk: SQLite concurrency regressions

Control: add concurrent budget, metering, audit, and cache tests before
changing database execution.

### Risk: a new shared folder becomes another dumping ground

Control: shared modules require at least two real consumers and must expose a
small documented contract. Provider-specific quirks stay with providers.

## Definition of done

The migration is complete only when:

1. `glc_v5` is no longer a runtime or build dependency.
2. The gateway repository contains the required GLC capabilities with the
   chosen history-preservation policy.
3. Every provider and channel has a clear owning folder containing its
   implementation, schemas, tests, configuration adapter, and documentation.
4. The LLM HTTP route delegates to a typed orchestration pipeline.
5. No monolithic replacement for `providers.py` or `chat.py` has been created.
6. Provider credentials remain isolated from channels, UI code, and agents.
7. Ports and internal service URLs resolve from one validated registry.
8. Duplicate enabled ports fail fast.
9. Existing GLC API contracts either remain supported or have a completed,
   documented caller migration.
10. HTTP, SSE, WebSocket, policy, budget, audit, cache, routing, channel, and
    voice regression tests pass.
11. Concurrent budget admission cannot overspend a configured ceiling.
12. Provider HTTP connections are reused and closed by application lifespan.
13. A semantic-cache miss generates no more than one embedding for the same
    prompt.
14. The original submodule and compatibility code are removed only after the
    rebuilt gateway is pushed and recoverable.

## Suggested commit boundaries

Keep commits narrow and reversible:

1. Gateway packaging and service registry.
2. GLC history import with no runtime changes.
3. Shared configuration/network/database infrastructure.
4. Security, audit, and control migration.
5. OpenAI provider vertical slice.
6. Remaining providers, one provider per commit where practical.
7. Chat-pipeline extraction by stage.
8. Channels, one channel per commit.
9. Voice, one provider per commit.
10. Port consolidation and compatibility listener.
11. Caller migration.
12. Old submodule and compatibility removal.

Every commit should leave the gateway runnable and its relevant tests green.
