# Plan 06 — Ingestion Domain Migration

## Goal

Move the active `merged-ingestion` application beneath Gateway ownership while
preserving its coordinator, review workflow, storage semantics, model-profile
rules, and `/api/ingestion/*` frontend contract.

## Important separation of concerns

> **Note from the ingestion roadmap (2026-09-27):** this plan, together with
> Plan 07, satisfies most of ingestion Stage A item 3 ("take UI ownership out
> of the ingestion repo"). The remaining loose ends are tracked in
> `To Do/Ingestion Pipeline to do/A3-ui-ownership-closeout.md`, which uses
> Plan 07's exit gate as its definition of done. The ingestion follow-on
> work (A1 judge gate, 03 MCP surface) targets the
> migrated code at `gateway/src/gateway/ingestion/`.

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

Today `ingestion-pipeline/merged-ingestion` is its own git repository (a
submodule of the AI OS parent), with its own `pyproject.toml`, lockfile, and
`.venv`, and Gateway reaches into it only via the sibling `sys.path`
injection that Plan 02 Work Package D isolates. This decision is whether,
after this plan, the *source itself* lives inside the Gateway repo (moved,
with history, per Plan 01's history policy) as the one canonical copy, or
whether it stays a separately versioned package that Gateway merely depends
on and mounts (like a normal third-party dependency).

- **Approve full Gateway ownership**: `gateway.ingestion` becomes real first-party code in this repo — no separate release process, no version pin to keep in sync, changes to ingestion and changes to Gateway can land in the same commit/PR when they need to.
- **Keep ingestion as a separately versioned package**: ingestion keeps its
own repo, versioning, and release cadence; Gateway depends on a specific
version of it, the way it might depend on any external library. More
process overhead (cutting releases just to pick up a fix), but keeps
ingestion usable outside Gateway without dragging the whole monorepo along.

**Confirmed: this already lands where you want it to.** The "Proposed
target" tree above puts ingestion at `gateway/src/gateway/ingestion/` — a
top-level package that is a *sibling* of `gateway/llm/`, not nested inside
it. Ingestion is not becoming part of the LLM orchestration code; it's its
own domain folder under `gateway/`, the same way `gateway/llm/` is its own
domain folder. No change needed to make that true — it was already the plan.

- [x] **Approve full Gateway ownership.**
- [ ] Keep ingestion as a separately versioned package mounted by Gateway.

**How you'll verify this landed:** if full ownership was chosen, `git log --follow` on any moved ingestion file shows continuous history through the
move (per Plan 01's history-preserving import policy) with no separate
version/release step required to pick up a change to it.

**Deviation from Plan 01's history-preserving import policy — accepted
2026-09-24:** the actual move was a plain file copy with mechanical import
rewrites (`from ingestion...` → `from gateway.ingestion...`), not a `git
subtree`/`git filter-repo` import staged through `gateway/_migration/`.
Verified: `gateway/src/gateway/ingestion/` is untracked with zero
`_migration` staging commit, and diffing old vs. new files (e.g.
`coordinator/gates.py`) shows only import-path changes, confirming a plain
copy. Content/behavior is unaffected — full ingestion suite (460/460) and
full Gateway suite (875 passed) pass unchanged. Aryaman explicitly accepted
losing linked git history in exchange for not re-doing the import: "I don't
really care about the history as long as the code is correct." `git log
--follow` on these files will not show pre-move history; the old commits
remain recoverable only inside the `ingestion-pipeline` submodule itself.

### 2. Internal model access

**Plain-English explanation, since this was confusing as written:**

- **"Named-profile semantics"** — ingestion never asks for a specific model
or provider directly. Every extraction call passes a *profile name*, e.g.
`knowledge-extraction-v1`, and whatever's on the other end of that call
looks up what that name actually means (which provider, which model,
temperature, etc.) from a profile catalogue. This is already true today —
`extraction/gateway.py` calls it "ground rule R1" and it's enforced in
code, not just convention. Nothing about this changes for ingestion. The
only question this decision answers is *what's on the other end of the
call* once ingestion moves in-process with Gateway.
- **What it will lead to / the difference it makes:** this doc originally
proposed the "inject an in-process object, skip the network hop" option as
the default. **That option was superseded.** Plan 04 decision #2 (the
general version of this same question, for every Gateway domain, not just
ingestion) was **decided by you on 2026-09-21, reversing an earlier
in-process tick: internal HTTP isolation, for everyone, always.** See
`04-glc-llm-orchestration-and-providers.md` decision #2 and
`04a-implementation-handoff.md`. This doc's proposed default below is now
corrected to match that decision instead of contradicting it.

Concretely, under HTTP isolation: `runner.py` keeps making a real HTTP
call — the same shape of call it makes today to GLC's port 8111 — except
the URL it targets changes from `http://127.0.0.1:8111` (GLC's private
port) to Gateway's own registry-resolved LLM address
(`/api/llm/chat`, per `config/services.yaml`). It is **not** handed a
Python object to call directly; it still serializes a request over a
socket, even though the call never leaves the same process. Ground rule R1
(always a named profile, never a raw provider call) is completely
unaffected — the profile name still travels in the request body exactly as
it does today.

**Why HTTP isolation over the in-process option, per the 2026-09-21
decision:** ingestion's `ChatClient` protocol and all seven of its
`.chat(...)` call sites are synchronous, while Gateway's own pipeline is
async — injecting a Python object would have forced a sync/async bridge.
Keeping everything on HTTP avoids that bridge entirely and keeps one
calling convention for every caller, in-process or not, at the cost of
paying JSON serialization and a loopback round-trip for a call that never
technically leaves the process. That cost is judged acceptable because
ingestion's extraction calls are already batched (default batch size 4),
so the overhead is amortized across several extractions per call, not paid
once per highlight.

Proposed default: preserve HTTP isolation. Ingestion keeps constructing an
HTTP-based client satisfying `ChatClient`, repointed at Gateway's own
registry-resolved LLM address instead of GLC's hardcoded port 8111. No
in-process `LLMService` object is injected into ingestion.

**Resolved which client module this is** (this was left open as §0.1 in
`06a-implementation-handoff.md`, now settled so Work Package D isn't
blocked): ingestion gets a **new, small HTTP client built under
`gateway/src/gateway/ingestion/`**, satisfying the exact same `ChatClient`
protocol — it does **not** continue importing `glc_v5/glc/client.py`.
Reasoning: this plan's own exit gate already required "no `glc-v5`,
`glc.client`, or port-8111 dependency," and ingestion was confirmed as the
only in-repo importer of `glc_v5/glc/client.py` outside `glc_v5`'s own
tests — so a new client satisfies both decision #2's literal text (*"an
HTTP-based client satisfying `ChatClient`"*, which doesn't require reusing
the same class) and this plan's exit gate, without anyone touching
`glc_v5/glc/client.py` itself (that file's fate is still Plan 07's call, not
this plan's — it simply ends up with zero in-repo importers after this
move).

- [ ] Approve an injected in-process LLM service.
- [x] **Preserve HTTP isolation for ingestion model calls, via a new
  Gateway-owned client (not a continued import of `glc_v5/glc/client.py`).**

**How you'll verify this landed:** `runner.py` constructs the new
`gateway.ingestion`-owned HTTP client (not an injected Python object, and
not `glc_v5/glc/client.py`) satisfying `ChatClient`, pointed at Gateway's
registry-resolved LLM address rather than the hardcoded
`127.0.0.1:8111`/`GLC_BASE_URL` default; `grep -rn "glc_v5\|glc\.client"
gateway/src/gateway/ingestion/` returns nothing. None of the seven
`.chat(...)` call sites across ingestion changes signature or becomes
`async`. A test that starts Gateway and runs an ingestion extraction
end-to-end shows a real inbound HTTP request in Gateway's own access/audit
log for each chat call.

### 3. Database ownership

Proposed default: Gateway owns lifecycle/configuration, while ingestion domain
repositories continue to own their schemas and queries. Physical data remains
under root `Database/`.

Unlike GLC (which Plan 01 found writing to `~/.glc/`, per Work Package F),
ingestion already writes correctly to `Database/sqlite/*.db` — this decision
is confirming that stays true, not fixing a problem. "Gateway owns
lifecycle/configuration" means Gateway's dependency container (Plan 02
decision #3) constructs ingestion's database connections at startup and
passes them in, rather than ingestion opening its own connections
independently the way it does as a standalone service today; the actual
schemas, migrations, and queries stay ingestion's own code, untouched.

- [x] **Approve this boundary.**
- [ ] Include a physical data migration; specify the destination below.

**How you'll verify this landed:** `Database/sqlite/*.db` continues to be
where ingestion's data lives — no new location, no schema changes — while
`grep` for ingestion opening its own top-level database connection (outside
what Gateway's lifespan/container hands it) turns up nothing new.

### 4. Route and frontend contract

Proposed default: keep `/api/ingestion/*` and `component6.v1` unchanged during
the move.

Today, `gateway/main.py` mounts ingestion's router (built by
`cockpit.server.create_router`) at `/api/ingestion`; the review response
includes a `contract_version` field whose value is `"component6.v1"`
(confirmed by `gateway/test_main.py`'s
`test_health_and_shell_are_available_but_ingestion_api_requires_bearer`,
which asserts exactly that). This decision is simply: does that path prefix
and version string survive the move to `gateway.ingestion` unchanged.

**Frontend location — out of scope for this move.** The ingestion review UI
already lives at the top-level `shell/` folder (`shell/src/screens/BookReview.tsx`,
`CleanupReview.tsx`, `KnowledgeProposalReview.tsx`, `ImageReview.tsx`,
`TextReview.tsx`, `GenericReview.tsx`, `PhaseHandoffReview.tsx`, plus
`shell/src/hooks/useIngestion.ts` and `shell/src/api/client.ts`) — it is not
embedded inside `ingestion-pipeline/merged-ingestion`. Confirmed:
`cockpit/server.py`'s own docstring states it "owns neither a FastAPI
application nor a frontend or port." This plan moves only backend code
(`ingestion-pipeline/merged-ingestion` → `gateway/src/gateway/ingestion/`);
`shell/` requires no changes and no file moves as part of this migration —
it already calls `/api/ingestion/*`, which Work Packages A–F keep stable.

- [x] **Preserve the current contract.**
- [ ] Approve a versioned replacement; describe it below.

**How you'll verify this landed:** `shell/` has no modified or moved files
as part of this plan's commits — its calls to `/api/ingestion/*` need no
code changes because the path and `component6.v1` version are unchanged.
`gateway/test_main.py`'s existing
assertion on `contract_version == "component6.v1"` still passes; the shell's
existing calls to `/api/ingestion/*` need no code changes on the frontend
side.

### 5. Internal structure timing

- [x] **Mechanical ownership move first; reader/writer refactor later.**
- [ ] Complete reader/writer boundaries before importing ingestion.

Proposed default, and the recommended/correct order: mechanical move first,
because the current 460-test baseline provides a strong equivalence gate.

**Why this is the correct order, not just the default:** ingestion's actual source layout today —
`src/ingestion/coordinator/` (with `coordinator.py`, `gates.py`,
`preflight.py`, `report.py`, `stages.py`, `state.py`), `extraction/`,
`sources/`, `consumers/`, `intake/`, `kg/`, `vector/`, `text_cleanup/` — is
what the "Proposed target" tree above mirrors almost folder-for-folder. If
you did the reader/writer refactor *first*, you'd be restructuring
`coordinator/` and `consumers/` while they're still governed by
ingestion's own 460-test suite in its old location — then moving the
already-restructured result, which conflates two kinds of risk (did the
move preserve behavior? did the refactor preserve behavior?) into one
change. Moving first, unrefactored, means the 460 tests are your equivalence
proof for the move alone.

**How you'll verify this landed:** whichever order was picked, check that
the reader/writer refactor (if it happens) has its own separate commit(s)
and its own equivalence gate, not fused into this plan's migration commits.

### 6. Dormant routing fields on the LLM request contract

*Raised by Plan 04's verification (*`04a-verification-report.md` *§3.1) and
deferred to here, because this plan is the moment a real caller repoints at*
`/api/llm/chat` *and the behaviour stops being theoretical.*

**Plain version of what's being asked, and the recommendation:** the
`/api/llm/chat` route accepts three request fields —
`auto_route`, `cost_quality_tradeoff`, `escalate` — that are meant to
control automatic model routing. That routing system isn't wired up yet
(Plan 04 decision #6 deliberately kept it dormant). Right now, if any
caller sends those fields, the server accepts them, validates them, and
then does nothing with them — the request runs as if they were never sent,
with no error and no indication the fields were dropped. The question is
just: what should the route do about that silence. Nothing about this
affects ingestion's own code either way — ingestion never sets these
fields (verified by grep, below) — this is purely about protecting *future*
callers of `/api/llm/chat` from silently losing an instruction they think
took effect. **Recommendation: pick the first option below — reject with a
400.** It costs nothing today (nobody calls it), and it turns a silent
trap into a loud, obvious error for whoever adds routing-aware code later.

Three fields on `ChatRequest` — `auto_route`, `cost_quality_tradeoff` and
`escalate` — are **accepted, validated, and then silently ignored**. They are
routing-tier controls, and Plan 04 decision #6 keeps `routing.yaml` carried
across but unwired, so nothing reads them. A caller that sets `auto_route`
today gets default-order provider selection and no indication that its
instruction was dropped. (`cache_system`, the fourth field in that report row,
was implemented during Plan 04b and is no longer in question.)

- [x] **Reject all three with a 400 while routing stays dormant.** *(Recommended.)*
- [ ] Keep accepting and ignoring them; document the no-op in the route's
  ```
  OpenAPI description so the silence is at least written down.
  ```
- [ ] Wire routing and implement them. *(Out of scope here — it reverses
  ```
  Plan 04's decision #6, "routing preserved, dormant".)*
  ```

**Why this is safe to decide now, with evidence:** rejecting them cannot break
ingestion, and cannot break anything else in the repo either.

```
$ grep -rn "auto_route\|cost_quality_tradeoff\|escalate" \
    ingestion-pipeline/ --include='*.py'
(no matches)

$ grep -rn "\.auto_route\|\.cost_quality_tradeoff\|\.escalate" \
    gateway/src/ --include='*.py'
orchestration/validation.py:21:  if request.profile and (... or request.auto_route):
```

**No in-repo caller passes any of the three**, and inside Gateway the only code
that *reads* one is the mutual-exclusion guard quoted above — the fields are
otherwise declarations in `llm/models.py` and nothing else. Repo-wide, the
remaining hits are `glc_v5/`'s own tests and two lines of `glc_v5/README.md`.

Ingestion in particular cannot be affected: `extraction/gateway.py`'s ground
rule R1 (Work Package D) means every model call names a profile such as
`knowledge-extraction-v1` — and `profile` together with `auto_route` is
*already* a 400 on both sides of the move (`glc_v5/glc/routes/chat.py:602` and
`gateway/.../orchestration/validation.py:21` raise the identical message). The
two are mutually exclusive by construction, so ingestion could not reach the
dormant path even if it wanted to.

The reason this still needs a tick rather than a default is reach, not current
use: `glc.client.LLM.chat()` ends with `**options: Any` splatted straight into
the request body (`glc_v5/glc/client.py:85-102`), so any caller can set these
keys without the client exposing them as named parameters. Silent-ignore is
therefore a trap that stays armed for every future caller, which is why the
recommendation is to make the dormancy loud.

**How you'll verify this landed:** if the 400 was chosen, `POST /api/llm/chat`
with `{"prompt": "hi", "auto_route": "decision"}` returns 400 with a message
naming routing as dormant, and a test asserts it; ingestion's extraction suite
is untouched either way, because it never sets the field. If silent-ignore was
chosen instead, the three fields carry an explicit "currently ignored"
description in the exported OpenAPI, so `migration/baseline/contracts/` records
the no-op rather than hiding it.

**Fixed while resolving your comments:** Work Package C and D below
previously described "the in-process `LLMService` from decision #2" being
injected into ingestion. Plan 04's decision #2 was **reversed on
2026-09-21** to internal HTTP isolation — ingestion keeps an HTTP-based
client and only its base URL changes. Decision #2 above and Work Packages C
and D have been corrected to match; no outstanding wording fix remains here.

## Work packages



### A. Characterize the Gateway/ingestion seam

- Freeze router/OpenAPI and frontend journey fixtures. *(Already captured
once, in Plan 01's* `migration/baseline/contracts/gateway-openapi.json` *—
this work package's job is re-confirming/extending that snapshot
specifically for ingestion's routes, not starting from nothing.)*
- Record public methods used by Gateway, scripts, and tests. *(Today*
`gateway/main.py` *calls exactly two things from ingestion:*
`config_from_environment()` *and* `create_router(service)`*, both from*
`cockpit.server` *(line 34) — that's the entire seam Gateway currently
depends on; this step is about whether anything else, e.g. a script or
test, reaches deeper into ingestion's internals than that.)*
- Characterize coordinator threading, close behavior, busy/stale responses,
evidence paths, retries, and crash recovery. *(This is about*
`src/ingestion/coordinator/coordinator.py` *and its siblings* `gates.py`*,*
`preflight.py`*,* `report.py`*,* `stages.py`*,* `state.py` *— pinning down exactly
how the coordinator behaves today, e.g. what a "busy" or "stale" response
looks like, before anything about how it's composed changes.)*
- Record configuration and root-database path precedence. *(E.g.*
`INGESTION_DATABASE_ROOT`*, which* `gateway/main.py`*'s* `_service()` *function
already defaults to* `AI_OS_ROOT / "Database"` *at line 47 — this work
package writes down that precedence rule explicitly rather than leaving it
implicit in one line of* `main.py`*.)*

**How you'll know Work Package A is done:** a document exists listing every
public method/attribute of `cockpit.server` and the coordinator that
anything outside ingestion currently touches — if Work Package C later
needs something not on that list, the characterization was incomplete.

### B. Import and package

- Import the reviewed ingestion history using Plan 01's policy.
- Preserve file layout in the first import commit.
- Establish `gateway.ingestion` packaging and dependency ownership.
- Replace sibling `sys.path` injection with normal imports. *(This is the
other half of Plan 02 Work Package D — the* `sys.path.insert` *block at*
`gateway/main.py` *lines 18–32, which today computes* `INGESTION_ROOT` *as
the sibling folder* `ingestion-pipeline/merged-ingestion` *and inserts it
into* `sys.path` *so* `from cockpit.server import ...` *works. Once ingestion
is a real subpackage of* `gateway`*, that whole block is deleted — the
import becomes an ordinary* `from gateway.ingestion... import ...`*.)*
- Keep a temporary compatibility package only where external imports require it.

**How you'll know Work Package B is done:** `grep -n "sys.path" gateway/`
finds nothing (the temporary adapter from Plan 02 Work Package D is now
gone, not just relocated); `import gateway.ingestion` works with the
package installed normally, no path manipulation required.

### C. Compose through Gateway dependencies

- Construct ingestion configuration and repositories through Gateway
lifespan. *(Today* `gateway/main.py`*'s* `_service()` *(line 37) builds a*
`ReviewService` *directly from* `config_from_environment()` *— after this
work package, that construction happens inside the shared lifespan/
container from Plan 02 decision #3, alongside every other domain's
services, rather than in ingestion-specific code sitting in the app entry
point.)*
- Repoint ingestion's LLM client at Gateway's own address. *(This is
decision #2 above, put into practice:* `runner.py`*'s*
`glc.client.LLM`-satisfying HTTP client stays an HTTP client — it is not
replaced by an injected object — but its base URL moves from GLC's
hardcoded* `127.0.0.1:8111`*/*`GLC_BASE_URL` *to Gateway's registry-resolved
LLM address at* `/api/llm/chat`*.)*
- Keep one shared model service per application, not one client per
extraction stage. *(Matches today's existing design already —* `runner.py`
*already documents building exactly one* `glc.client.LLM` *and sharing it
across the run; this just says the in-process replacement must preserve
that "one shared instance" property, not regress to constructing a new
client per call.)*
- Mount the existing router through a domain route factory. *(Same*
`cockpit.server.create_router(service)` *call, but produced by ingestion's
route factory function rather than called directly from* `gateway/main.py`
*— the Plan 02 Work Package B pattern applied to ingestion specifically.)*
- Close executors, stores, database clients, and model dependencies cleanly.
*(Today* `main.py`*'s* `lifespan` *only calls* `service.close()` *on shutdown,
line 61 — verify that single call still closes everything it needs to
once ingestion owns more of its own resources under Gateway's container.)*

**How you'll know Work Package C is done:** starting and then stopping
Gateway leaves no dangling ingestion database connections, threads, or
executors behind (checkable by watching open file descriptors/threads
across a start-stop cycle); `gateway/test_main.py`'s ingestion tests pass
unchanged against the newly-composed wiring.

### D. Replace the GLC package dependency

- Replace dynamic `glc.client` construction. *(*`runner.py`*'s*
`import_module("glc.client")` *call and its error message — "The shared
glc.client.LLM package is not importable" — go away because ingestion no
longer imports a separate* `glc` *package at all; per decision #2 (HTTP
isolation), it keeps a plain HTTP client of the same* `ChatClient` *shape,
just pointed at Gateway's own* `/api/llm/chat` *instead of GLC's port.)*
- Preserve named-profile-only routing guards. *(*`extraction/gateway.py`*'s
"ground rule R1" — every model call names a profile like*
`knowledge-extraction-v1`*, never a raw provider call — must hold exactly
as true after this move.)*
- Move required chat and embedding profiles into the Gateway catalogue.
*(Specifically* `knowledge-extraction-v1` *from* `glc_v5/glc/profiles.yaml`*,
plus whatever embedding profile ingestion's chunking uses — these need to
exist in Gateway's profile catalogue by the time ingestion's code runs
against it, or every extraction call fails immediately.)*
- Convert cross-project GLC tests into Gateway-domain contract tests.
- Remove `glc-v5` from ingestion dependency metadata. *(Concretely, delete
the two lines in* `ingestion-pipeline/merged-ingestion/pyproject.toml`*:*
`"glc-v5>=0.5.0"` *in the dependency list, and*
`glc-v5 = { path = "../../glc_v5", editable = false }` *in the tool-specific
source section.)*
- Update environment verification and live-smoke scripts.

**How you'll know Work Package D is done:** today,
`grep -rn "glc-v5\|glc\.client\|GLC_BASE_URL" ingestion-pipeline/merged-ingestion/pyproject.toml ingestion-pipeline/merged-ingestion/src` returns the two `pyproject.toml`
lines above, plus `runner.py`'s import and default URL — the same search,
run against wherever this content actually lives once Work Package B has
moved it (the old submodule path if it's still the working copy, or
`gateway/`'s new package metadata if the move is complete), should return
nothing. Running an extraction end-to-end still produces the same
`ClaimProposal`/`ConceptProposal`/`RelationProposal` output shape it does
today, proving the profile catalogue move didn't silently change which
model answers `knowledge-extraction-v1`.

### E. Preserve data and processing semantics

This whole work package is a constraint on Work Packages B–D, not new work
of its own: none of the actual behavior in
`src/ingestion/coordinator/gates.py` (review/judge gates), `kg/`, `vector/`,
`text_cleanup/`, or `consumers/` (destination writers) should differ before
and after the move — only *how* ingestion is wired into Gateway changes.

- No changes to immutable capture rules.
- No changes to review/judge gates.
- No changes to duplicate/version semantics.
- No changes to KG, vector, content, page-scanner, or cleanup schemas.
- No changes to sequential coordinator behavior.
- Verify retry skips destinations already written successfully. *(A
concrete, checkable behavior: if a run writes to the KG store successfully
but fails before writing to the vector store, a retry of that run must
not re-write to the KG store — only pick up where it left off.)*

**How you'll know Work Package E is done:** the full existing ingestion test
suite (460 tests, per the roadmap's verified baseline) passes unchanged
against the migrated code; a specific retry test — kill a run after one
destination succeeds, retry it, and assert that destination wasn't written
twice — passes.

### F. Verification

- Complete ingestion suite under its new package path. *(All ~460 tests,
run from wherever* `gateway.ingestion`*'s new location says they should be
run from — not* `ingestion-pipeline/merged-ingestion` *anymore.)*
- Gateway API and OpenAPI suites. *(*`gateway/test_main.py`*,*
`gateway/test_contract_staleness.py`*, and an export via*
`gateway/export_openapi.py` *diffed against*
`migration/baseline/contracts/gateway-openapi.json`*.)*
- Real shell review journey. *(Load* `http://127.0.0.1:8000/ingestion` *in a
browser and click through an actual review — the same manual check
described in Plan 02 Work Package E, now with ingestion fully composed
in-process rather than through the temporary sibling-path adapter.)*
- In-process LLM structured extraction and embedding tests with fake
providers. *(Tests exercising* `extraction/gateway.py`*'s*
`_ExtractedConcept`*/*`_ExtractedClaim`*/*`_ExtractedRelation` *validation
against a fake* `LLMService` *implementing the* `ChatClient` *protocol — no
real provider call needed to prove the wiring works.)*
- Storage preflight, failure, recovery, and idempotency tests.

**How you'll know this plan is done:** every command that currently proves
ingestion works (`pytest`, `mypy --strict cockpit/server.py`, per
`gateway/README.md`'s regression commands) still passes, run from
ingestion's new location under `gateway/`; the manual shell review journey
completes end-to-end with no visible behavior change from today.

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