# Plan 03 — GLC Platform, Security, Audit, and Control

## Related decisions

Always-on and fail-hard by design (see §2 below) — this plan is explicitly
**not** part of the "dormant unless activated" treatment that Plan 05 applies
to channels and voice; security, audit, and control are not optional
surfaces. The "no hard-wiring between GLC's own internal components" program
rule in `00-program-roadmap.md` applies here too: platform/security/audit/
control must stay decoupled from each other and from the LLM orchestration
path Plan 04 moves later, not just decoupled from ingestion and the outer
Gateway.

## Goal

Import GLC into the Gateway repository and move its shared infrastructure and
safety-sensitive domains behind Gateway-owned interfaces. The LLM provider and
chat implementation remain on the old path during this plan.

## Why this comes before model providers

Profiles, providers, channels, and chat all depend on configuration, databases,
policy, audit, security, and lifecycle behavior. Moving those foundations first
prevents the later LLM migration from creating a second set of globals.

## Decisions required before implementation

### 1. Database layout

GLC currently uses separate SQLite responsibilities for gateway calls, audit,
budgets, cache, pairing, and channel state.

Proposed default: keep separate domain repositories and schemas. Share only
connection/migration primitives. Do not merge the data into one mega-schema.

- [ ] Approve domain-owned repositories.
- [ ] Intentionally consolidate selected databases; list them below.

This decision is downstream of Plan 01 Work Package F (GLC's ledger and
audit SQLite files currently live at `~/.glc/`, not under `Database/`).
Resolve that location decision in Plan 01 before finalizing this one.

### 2. Failure policy

GLC currently boots many optional capabilities fail-soft, while malformed
budget configuration is surfaced because silently disabling a ceiling is
dangerous.

Proposed default:

- Fail startup for invalid security-critical configuration.
- Start degraded for unavailable optional telemetry/cache integrations.
- Report every degraded subsystem through readiness diagnostics.

- [ ] Approve this policy.
- [ ] List domains that must always fail hard or always fail soft.

### 3. Policy reload

Proposed default: preserve SIGHUP reload temporarily and add an authenticated
control operation that invokes the same service method.

- [ ] Preserve SIGHUP plus API reload.
- [ ] API-only reload.
- [ ] Restart-only configuration.

### 4. Legacy GLC import visibility

Proposed default: old `glc.*` modules become compatibility adapters and may
delegate to Gateway services, but new Gateway domains never import back from
legacy modules.

- [ ] Approve one-way dependency enforcement.
- [ ] Specify exceptions below.

## Work packages

### A. History-preserving import

- Import the reviewed GLC state using Plan 01's chosen history policy.
- Verify important file history.
- Keep the original submodule and standalone service runnable.
- Add dependency-direction tests before reorganizing code.

### B. Platform infrastructure

- Move configuration resolution.
- Introduce shared database and migration primitives.
- Introduce lifespan-managed outbound HTTP clients.
- Move telemetry initialization and shutdown.
- Add readiness aggregation and structured startup errors.

### C. Security and policy

- Move trust classification, allowlists, pairing, rate limits, and SSRF rules.
- Move policy schemas, configuration, evaluation, and reload behavior.
- Keep channel/vendor signature verification within its integration package.
- Add authorization and refusal characterization tests.

### D. Audit and control

- Move audit storage and query interfaces.
- Move control operations and routes.
- Define kill/presence/pairing behavior within the unified Gateway lifecycle.
- Ensure audit failures have an explicit fail-open or fail-closed policy.

### E. Compatibility delegation

- Make selected old GLC endpoints delegate to the new Gateway-owned services.
- Preserve old errors, status codes, and environment variables.
- Do not proxy in-process calls over HTTP when a direct service adapter is
  sufficient.

## Explicitly out of scope

- Moving model providers.
- Splitting the chat route.
- Moving channels or voice.
- Moving ingestion.
- Database engine replacement.

## Exit gate

- Gateway owns lifecycle, configuration, security, policy, audit, and control.
- New modules do not import legacy `glc.*` implementations.
- Old routes pass preserved contract tests through compatibility adapters.
- Startup, shutdown, degraded-mode, and security failure behavior are tested.
- GLC standalone remains runnable as rollback protection.

## Aryaman's comments

Add database, security, failure-mode, policy, and control requirements here.

