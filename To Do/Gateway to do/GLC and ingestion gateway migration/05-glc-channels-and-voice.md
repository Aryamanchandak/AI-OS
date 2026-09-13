# Plan 05 — GLC Channels and Voice

## Related decisions

Explicitly excluded from the "always-on, fail-hard" treatment Plan 03 gives
security/audit/control — see `00-program-roadmap.md`'s program rules and
Plan 03's "Related decisions." This is the one plan in the sequence where
"moved" and "activated" are deliberately different states.

## Goal

Move channel and voice capabilities beneath Gateway while preserving their
native contracts, long-running lifecycles, signature validation, trust policy,
and secret isolation.

## Decisions required before implementation

### 1. In-process versus worker boundary

Proposed default:

- Simple webhook adapters mount in the Gateway process.
- Long-running pollers and integrations with failure-prone native dependencies
  may run as supervised workers.
- Both use the same Gateway-owned channel contracts and security services.

- [ ] Approve capability-based process boundaries.
- [ ] Require every channel in-process.
- [ ] Require every channel as a separate worker.

### 2. Channel migration order

Proposed default: first migrate one simple webhook channel and one long-running
or WebSocket channel to prove both lifecycle patterns; then migrate remaining
channels individually.

- [ ] Approve this proof-slice approach.
- [ ] Name the first two channels below.

### 3. Channel-to-agent bridge

GLC currently contains an S16 agent bridge. Its ownership and failure policy
must be explicit before channel movement.

- [ ] Keep the bridge in Gateway channels as an injected downstream service.
- [ ] Move it to the agent runtime and have Gateway publish canonical events.
- [ ] Define another boundary below.

### 4. Voice transport

- [ ] Preserve current request/response STT and TTS routes first.
- [ ] Include real-time voice/WebSocket redesign in this plan; describe the
      desired contract below.

Proposed default: real-time voice redesign is separate because the current
documentation identifies portions of it as not yet implemented.

### 5. Activation state after migration

Aryaman is not using most channels today (e.g. WhatsApp) and doesn't want
code that's merely been moved to become live by default. This is a distinct
question from decisions 1–4 above (which decide *how* a channel would run if
active) and from whether it gets tested (it does, unconditionally).

Proposed default: every channel and voice adapter is registered with Gateway
but **not mounted / not started** by default after migration — enabling one
is an explicit, separate configuration action, not a side effect of the move
landing. Each still passes the same characterization tests before this
plan's exit gate as if it were active; "dormant" describes what's running,
not what's tested.

- [ ] Approve dormant-by-default with characterization tests still required.
- [ ] Name any channel that should be active immediately upon migration.

## Work packages

### A. Shared channel core

- Canonical message, attachment, reply, and error contracts.
- Channel adapter and transport protocols.
- Registry and discovery.
- Pairing, trust, generic rate limiting, and audit integration.
- Route/service boundary for send, webhook, WebSocket, and administration.

### B. Move channel packages vertically

For each channel, keep together:

- Native schemas and translation.
- Signature/authentication logic.
- Provider client or injected transport.
- Artifact handling.
- Setup tooling and environment adapter.
- Tests, documentation, and development harnesses.

Do not expose stored credentials through administration or diagnostics.

### C. Worker lifecycle

- Define registration, readiness, restart, shutdown, and backoff behavior.
- Resolve worker addresses from the service registry.
- Test shutdown during an active poll, webhook, or WebSocket session.
- Ensure a broken optional adapter cannot prevent unrelated Gateway domains
  from starting unless explicitly configured as required.

### D. Voice

- Define shared STT and TTS contracts.
- Move providers one at a time with provider-local configuration and tests.
- Preserve `/v1/transcribe` and `/v1/speak` behavior.
- Preserve audio limits, timeouts, errors, and fallback order.

### E. UI and administration

- Decide which GLC static pages become React shell pages.
- Preserve necessary channel setup and health information.
- Remove duplicated static pages only after equivalent UI/API capability exists.

## Explicitly out of scope

- Ingestion movement.
- Agent-runtime redesign unless selected in decision 3.
- New channels or voice providers.
- Unimplemented real-time voice features unless explicitly approved.

## Exit gate

- Runtime channel and voice implementations do not import legacy `glc.*` code.
- Webhook signatures, WebSocket behavior, polling, send, STT, and TTS contracts
  pass preserved tests.
- Secrets remain provider-local and redacted.
- Worker startup and shutdown behavior is supervised and observable.
- Optional integration failure does not take down unrelated Gateway domains.
- Every channel and voice adapter is registered but disabled by default
  (decision 5), with no exceptions left undeclared.

## Aryaman's comments

Name first-migration channels, required workers, bridge ownership, secret
rules, and voice expectations here.

