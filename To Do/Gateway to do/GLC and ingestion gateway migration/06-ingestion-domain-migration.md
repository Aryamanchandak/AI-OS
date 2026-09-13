# Plan 06 — Ingestion Domain Migration

## Goal

Move the active `merged-ingestion` application beneath Gateway ownership while
preserving its coordinator, review workflow, storage semantics, model-profile
rules, and `/api/ingestion/*` frontend contract.

## Important separation of concerns

This plan moves ownership and composition. It does **not** also perform the
reader/writer boundary refactor, staging/batching redesign, MCP expansion, or
event-driven ingestion described in the ingestion roadmap. Those are separate
behavioral/architectural projects and should operate on the migrated domain
after this move unless Aryaman explicitly changes the sequence.

## Proposed target

```text
gateway/src/gateway/ingestion/
├── api/
├── coordinator/
├── pipeline/
├── extraction/
├── sources/
├── consumers/        # renamed to destinations only in a later refactor
├── intake/
├── kg/
├── vector/
├── text_cleanup/
└── persistence/
```

The precise internal folders should initially follow the current package to
keep the import mechanical. Reorganization belongs in later, focused commits.

## Decisions required before implementation

### 1. Physical ownership

Proposed default: import the complete active `merged-ingestion` history into
the Gateway repository and make it the canonical implementation. Retire the
submodule only in Plan 07.

- [ ] Approve full Gateway ownership.
- [ ] Keep ingestion as a separately versioned package mounted by Gateway.

### 2. Internal model access

Proposed default: inject the `gateway.llm` service using the same named-profile
semantics currently enforced around `glc.client.LLM`. Do not make ingestion
call the Gateway's own HTTP port.

- [ ] Approve an injected in-process LLM service.
- [ ] Preserve HTTP isolation for ingestion model calls.

### 3. Database ownership

Proposed default: Gateway owns lifecycle/configuration, while ingestion domain
repositories continue to own their schemas and queries. Physical data remains
under root `Database/`.

- [ ] Approve this boundary.
- [ ] Include a physical data migration; specify the destination below.

### 4. Route and frontend contract

Proposed default: keep `/api/ingestion/*` and `component6.v1` unchanged during
the move.

- [ ] Preserve the current contract.
- [ ] Approve a versioned replacement; describe it below.

### 5. Internal structure timing

- [ ] Mechanical ownership move first; reader/writer refactor later.
- [ ] Complete reader/writer boundaries before importing ingestion.

Proposed default: mechanical move first because the current 460-test baseline
provides a strong equivalence gate.

## Work packages

### A. Characterize the Gateway/ingestion seam

- Freeze router/OpenAPI and frontend journey fixtures.
- Record public methods used by Gateway, scripts, and tests.
- Characterize coordinator threading, close behavior, busy/stale responses,
  evidence paths, retries, and crash recovery.
- Record configuration and root-database path precedence.

### B. Import and package

- Import the reviewed ingestion history using Plan 01's policy.
- Preserve file layout in the first import commit.
- Establish `gateway.ingestion` packaging and dependency ownership.
- Replace sibling `sys.path` injection with normal imports.
- Keep a temporary compatibility package only where external imports require it.

### C. Compose through Gateway dependencies

- Construct ingestion configuration and repositories through Gateway lifespan.
- Inject the LLM service/profile resolver.
- Keep one shared model service per application, not one client per extraction
  stage.
- Mount the existing router through a domain route factory.
- Close executors, stores, database clients, and model dependencies cleanly.

### D. Replace the GLC package dependency

- Replace dynamic `glc.client` construction.
- Preserve named-profile-only routing guards.
- Move required chat and embedding profiles into the Gateway catalogue.
- Convert cross-project GLC tests into Gateway-domain contract tests.
- Remove `glc-v5` from ingestion dependency metadata.
- Update environment verification and live-smoke scripts.

### E. Preserve data and processing semantics

- No changes to immutable capture rules.
- No changes to review/judge gates.
- No changes to duplicate/version semantics.
- No changes to KG, vector, content, page-scanner, or cleanup schemas.
- No changes to sequential coordinator behavior.
- Verify retry skips destinations already written successfully.

### F. Verification

- Complete ingestion suite under its new package path.
- Gateway API and OpenAPI suites.
- Real shell review journey.
- In-process LLM structured extraction and embedding tests with fake providers.
- Storage preflight, failure, recovery, and idempotency tests.

## Explicitly out of scope

- Reader/writer restructuring.
- Pipeline staging/batching redesign.
- MCP tools and event triggers.
- Database schema or engine replacement.
- Parallelizing the coordinator.

## Exit gate

- Gateway owns and imports ingestion normally.
- No production `sys.path` injection points at the old project.
- Ingestion has no `glc-v5`, `glc.client`, or port-8111 dependency.
- `/api/ingestion/*` and the shell journey are unchanged.
- The complete ingestion and Gateway suites pass.
- The old ingestion submodule remains available only as rollback protection.

## Aryaman's comments

Add corrections to ingestion ownership, LLM call boundaries, database paths,
review behavior, and which refactors must happen before or after the move.

