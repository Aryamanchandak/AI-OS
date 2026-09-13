# Plan 07 — Runtime Cutover and Legacy Removal

## Goal

Make the unified Gateway the canonical runtime, migrate every known caller,
observe the compatibility boundary, and remove the old GLC and ingestion
submodules only when they are no longer required.

## Decisions required before implementation

### 1. Final process model

- [ ] One Gateway process on port 8000 plus explicitly configured workers.
- [ ] Separate LLM and ingestion processes behind Gateway routing.
- [ ] Another deployment model described below.

Proposed default: in-process domains on 8000; separate only long-running or
failure-sensitive workers that have a documented operational reason.

### 2. Port 8111 transition

Proposed default: keep a temporary compatibility listener or proxy only while
observed callers remain. Instrument it, warn on use, then remove it.

- [ ] Approve observed-usage cutover.
- [ ] Remove 8111 on a fixed release/date.
- [ ] Keep 8111 permanently as an alias.

### 3. Legacy Python imports

Proposed default: retain a thin `glc.client` compatibility package only long
enough for external Python callers to migrate; prohibit it in Gateway-owned
production code immediately.

- [ ] Approve temporary Python compatibility.
- [ ] Remove all `glc.*` imports at the HTTP cutover.

### 4. Archival policy

- [ ] Remove submodules after their replacements are pushed and tagged.
- [ ] Retain read-only archived directories in the parent repository.
- [ ] Retain only external source repositories/tags.

## Work packages

### A. Make service registry authoritative

- Resolve Gateway and worker ports from one validated configuration.
- Update launchd, systemd, Windows, Docker, demo, and local scripts.
- Remove copied production literals for port 8111.
- Add authenticated service-health diagnostics.

### B. Migrate callers

- Update ingestion, S16/agent runtime, scripts, shell, tests, desktop tools,
  and documentation.
- Replace direct `glc.*` imports with supported Gateway clients/contracts.
- Record owner and completion evidence for every Plan 01 caller.

### C. Run compatibility observation

- Instrument legacy HTTP and Python compatibility use without logging content
  or secrets.
- Exercise HTTP, SSE, and WebSocket behavior through any temporary proxy.
- Define the no-usage observation window.
- Publish deprecation messages and final cutover instructions.

### D. Operational readiness

- Cold start, restart, shutdown, and crash recovery.
- Provider/channel worker isolation.
- Health/readiness behavior under partial failure.
- Concurrent budget, audit, cache, and ingestion database activity.
- Backup/restore and configuration rollback.
- Secret redaction and least-privilege review.

### E. Remove legacy boundaries

- Remove the 8111 listener after its approved exit condition.
- Remove `glc.client` compatibility after its caller inventory reaches zero.
- Remove starts of `glc.main`.
- Remove obsolete environment aliases.
- Remove GLC and ingestion submodules and update `.gitmodules` deliberately.
- Archive/tag source repositories according to decision 4.
- Replace legacy documentation with Gateway-domain documentation.

## Required final verification

- Gateway, ingestion, GLC-preserved contract, frontend, type, and lint suites.
- OpenAPI comparison with intentional differences approved.
- Chat, structured output, embed, batch, SSE, WebSocket, webhook, STT, TTS,
  budgets, cache, audit, and ingestion end-to-end tests.
- Search proving no production dependency on `glc_v5`, the old ingestion
  package, `glc.main`, or copied port 8111.
- Fresh-machine/bootstrap test using only canonical Gateway instructions.

## Exit gate

- Unified Gateway is the sole documented application entry point.
- Every active caller uses a supported Gateway contract.
- Compatibility traffic is zero for the approved observation window.
- Old submodules are unnecessary for build, test, runtime, and operation.
- Replacement commits are pushed, tagged, and recoverable before deletion.
- Rollback and backup procedures have been exercised.

## Aryaman's comments

Specify the final process model, observation window, retirement policy, and any
caller that must retain a legacy interface here.

