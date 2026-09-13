# GLC and Ingestion Under Gateway — Program Roadmap

## Purpose

This folder splits the Gateway restructuring into reviewable plans. Each plan
has one architectural concern, explicit decisions, a bounded implementation
scope, and an exit gate. No later plan should begin until the previous plan's
decisions and exit evidence have been reviewed.

The existing `../01-dismantle-glc-v5-into-gateway.md` remains the source
reference. It should not be executed as one change set.

## Target outcome

This plan sequence covers GLC becoming part of Gateway, and — as its own
later, isolated phase (Plan 06) — ingestion coming under Gateway too. These
stay two separate moves with two separate exit gates; nothing in Plans 02–05
depends on ingestion internals, and Plan 06 does not redesign GLC.

The AI OS Gateway becomes the application and repository boundary for:

- LLM routing, profiles, providers, cache, budgets, and metering (`gateway.llm`,
  Plan 04) — exposed to any caller, in or out of the Gateway process, through
  one of two supported surfaces: an in-process typed `LLMService` for code
  that lives inside Gateway, and a versioned, minimal-dependency Gateway
  client SDK for everything else (future agents, scripts, other repos). See
  Plan 04 for both.
- Security, audit, and control (Plan 03) — always-on, fail-hard for
  security-critical configuration. Not part of the dormancy decision below.
- Channels and voice (Plan 05) — moved under Gateway but **registered
  disabled by default** (not mounted, no worker started) until explicitly
  turned on. Aryaman doesn't use most of these today and doesn't want them
  live just because the code moved. Dormant does not mean untested: each
  channel still gets the same characterization tests as everything else
  before Plan 05's exit gate, so turning one on later isn't a leap of faith.
- The ingestion API, coordinator, pipeline, readers, and destination writers
  (Plan 06). Ingestion is **not** a GLC subcomponent — it's a peer caller of
  GLC's LLM domain today (via `glc.client.LLM` over HTTP; see
  `ingestion/extraction/gateway.py` and `ingestion/runner.py`), and stays a
  peer after the move (via the in-process `LLMService`, per Plan 04). Any
  functionality that is genuinely a Gateway function belongs in Gateway,
  called through an explicit interface — not duplicated or wired ad hoc into
  ingestion's own code.

The final system does not require the standalone `glc_v5` or
`ingestion-pipeline` submodules to build, test, or run.

Explicitly **not** covered here: the React shell itself, and how it presents
login/auth state, both belong to `To Do/UNIFIED UI/UNIFIED_UI_PLAN.md`. What
*is* covered here is the backend authentication boundary — which scheme
applies to which class of caller (Gateway bearer token for internal/admin
APIs, provider-native signatures for inbound webhooks, no token at all for
in-process calls) — decided in Plan 02 §2. The shell consumes that policy; it
doesn't define it.

## Plan sequence

1. **Baseline and ownership decisions**
  Protect current work, choose history/import policy, inventory callers, and
   freeze compatibility contracts. Also inventories which functionalities
   are moved-and-active versus moved-and-dormant (see program rules below),
   and settles where GLC's own SQLite files land (see the corrected baseline
   note below — they are not in `Database/` today).
2. **Gateway foundation**
  Make Gateway a packaged application with dependency injection, lifecycle,
   configuration, service discovery, and the existing ingestion surface.
   This is the empty, packaged container — it imports no GLC runtime code.
   Resolved: no further split needed. Plan 03 already excludes channels,
   voice, ingestion, and providers from its own scope, and Plan 05 is
   already the isolated "optional/dormant" phase — the split you'd want is
   the one that already exists between Plan 03 (always-on foundation) and
   Plan 05 (dormant by default). See Plan 02's own "Related decisions" note.
3. **GLC platform, security, audit, and control**
  Move shared runtime infrastructure and safety-sensitive domains before the
   model orchestration path. Always-on and fail-hard by design (see Plan 03
   §2) — explicitly not part of the "dormant unless activated" treatment
   that applies to Plan 05.
4. **GLC LLM orchestration and providers**
  Move providers vertically, split the chat monolith, and preserve all model
   API contracts. Difference from Plan 02: Plan 02 builds the empty,
   packaged container (DI, lifecycle, config); Plan 04 is what moves the
   actual GLC LLM code — providers, routing, the chat pipeline — into that
   container. Plan 04 depends on Plan 02's dependency container existing
   first; they can't be merged for that reason. Plan 04 also formalizes the
   Gateway client SDK and the profile-to-routing-tier decision (see Plan 04's
   own "Related decisions" and new decision items).
5. **GLC channels and voice**
  Move channel and voice integrations with their worker, webhook, streaming,
   and secret-isolation requirements, registered but disabled by default
   until explicitly activated (see Plan 05's new decision item). Good
   candidate for background/async work later, since it's self-contained and
   doesn't block anything else in this sequence.
6. **Ingestion domain migration**
  Move ingestion ownership under Gateway without combining that move with
   the separate reader/writer or event-driven redesigns.
7. **Runtime cutover and legacy removal**
  Consolidate ports, migrate callers, remove compatibility layers only after
   observed usage reaches zero, and retire the old submodules.



## Program rules

- Structural moves and behavioral improvements are separate commits.
- Existing HTTP, SSE, WebSocket, profile, error, and review contracts remain
stable until an intentional replacement is approved.
- Each plan begins with characterization tests and ends with the complete
relevant test suites passing.
- No submodule is removed until its replacement is pushed and recoverable.
- Secrets are injected only into the domain/provider that owns them.
- Gateway composition may be one process, but operationally distinct workers
may remain separate when isolation or lifecycle requirements justify it.
- The root `Database/` remains the data location unless a separate storage
migration is explicitly approved.
- No hard-wiring between GLC's own internal components either. The
  Gateway↔GLC↔ingestion boundaries are not the only ones that need a
  standard interface — GLC's providers, routing, cache, and economics must
  stay decoupled from each other the same way (e.g. through protocols, the
  way `ingestion/extraction/gateway.py`'s `ChatClient` protocol already
  decouples ingestion from GLC's concrete client). This is what keeps a
  future "make this component an MCP call" decision a matter of swapping one
  injected dependency, not a rewrite — and it's why the mandatory
  logging/audit stage in Plan 04's chat pipeline (stage 9) is written as a
  non-optional pipeline step rather than a bolt-on: an LLM call being logged
  must not depend on how any one component happens to be wired today.



## Current verified baseline

Verified on 2026-09-13:

- Gateway: 27 tests passed.
- Ingestion: 460 tests passed.
- GLC: 563 tests passed, 16 skipped.
- Gateway currently mounts ingestion through sibling `sys.path` injection.
- Ingestion currently installs `glc-v5` and calls `glc.client.LLM`.
- GLC currently runs as a separate FastAPI service on port 8111.
- Gateway and both submodules contain uncommitted/untracked work that must be
resolved in Plan 01.
- **Correction (2026-09-14):** the "root `Database/` remains the data
  location" rule above describes intent, not current fact, for GLC. Verified
  in the code: GLC's call ledger defaults to `~/.glc/gateway.sqlite`
  (`glc_v5/glc/db.py`) and its audit log to `~/.glc/audit.sqlite`
  (`glc_v5/glc/audit/store.py`) — neither `GLC_GATEWAY_DB` nor
  `GLC_AUDIT_DB` has ever been pointed at `Database/`. Ingestion, by
  contrast, already writes into `Database/sqlite/*.db` correctly. This is an
  open decision for Plan 01/03, not a settled baseline: `db.py`'s own
  docstring says the `~/.glc` location is deliberate — "so the gateway is
  installable as a daemon without writing into the source tree" — which may
  be a real reason to keep it there rather than an oversight. Plan 01 must
  decide, not assume.



## Program-level decisions for Aryaman

- [ ] Approve this seven-plan sequence, or specify which plans should be
      combined or split further.
- [ ] Confirm whether the desired end state is one deployable Gateway process
      plus optional workers, or multiple always-separate services behind one
      Gateway address.
- [ ] Confirm whether `/v1/*` is a permanent public/internal contract or a
      temporary compatibility surface that may eventually be removed.
- [ ] Confirm whether the root `Database/` layout is explicitly out of scope.



## Aryaman's comments

Add program-wide corrections, constraints, or desired end-state details here.