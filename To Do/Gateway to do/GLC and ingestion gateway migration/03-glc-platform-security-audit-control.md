# Plan 03 — GLC Platform, Security, Audit, and Control

**Status: CLOSED — 2026-09-22.** Implementation and verification evidence is recorded in
`03-verification-report.md`. The post-implementation decision waived pre-import `git blame` preservation;
the working snapshot and its Gateway commits are the accepted history boundary.

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

**Revised per feedback (2026-09-16): the previous draft here committed to
importing the entire GLC submodule verbatim in one shot — full tree, every
file, nothing pruned at import time — before any re-architecture started.
That's a stronger claim than "lift and shift" was meant to authorize.** The
worry, stated directly: a coding agent asked to overhaul a domain that's
sitting inside a giant, still-mostly-untouched import of an entire other
codebase struggles to actually change anything, because it can't tell what's
load-bearing from what's dead weight — the whole point of doing this
migration in scoped plans (03 platform/security/audit/control, 04 LLM/
providers, 05 channels, 06 ingestion) was to keep each overhaul bounded and
cheap, and a full verbatim dump undoes that.

Plan 01 §1 ("Preserve full history") names two possible mechanisms —
`git subtree` or `git filter-repo` — without picking one. That distinction
matters here: `git subtree` can only bring in the whole source tree at the
commit(s) it's pointed at. `git filter-repo` is a history *rewrite* tool
whose primary use is path-filtering — it can produce an import that contains
only the paths this plan actually needs (`glc/config.py`, `glc/db.py`,
`glc/audit/`, `glc/security/`, `glc/policy/`, `glc/routes/control.py`, and
their tests), with full commit history for exactly those paths, and nothing
else. So "lift only the useful bits" and "preserve full history for what you
bring" are not in tension — they just require `filter-repo` specifically,
not `subtree`, for the import mechanism.

- [ ] **Path-filtered import.** Waived after implementation; no history rewrite or re-import is required. Use `git filter-repo` scoped
  ```
  to the paths this plan's Work Packages B–D actually move — platform
  config/DB/HTTP/telemetry, security/policy, audit/control, plus their
  tests. Full git history is preserved for exactly those paths (`git
  blame`/`log -p` work on them going forward); nothing else lands yet.
  Provider/chat code gets its own `filter-repo` pass, scoped the same
  way, when Plan 04 actually needs it — not before. Cost: multiple
  import passes across plans instead of one; each pass is small and
  independently reviewable, which is the point.
  ```
- [ ] **Full-tree import, then prune.** Bring in the entire GLC tree in one
  ```
  commit (as the previous draft proposed), then delete what each work
  package doesn't need as it goes. Rejected default: this is what
  produced the worry above — the deletion happens *after* the coding
  agent has to work inside the full tree, not before.
  ```
- [x] **Snapshot only, no pre-import history (confirmed 2026-09-22).** Import the current file contents with a
  ```
  pointer to the source commit, no per-file history. Simplest, but loses
  `git blame` on GLC code entirely — likely stronger than what Plan 01
  §1 already committed to, so treat this as a Plan 01 reopening, not a
  Plan 03 call.
  ```

**Final outcome:** the snapshot option above supersedes the earlier path-filtered-import discussion. The
implementation is retained as-is; no `filter-repo` rewrite or re-import is part of closure.

**Cross-plan consequence, flagged rather than silently resolved:** picking
path-filtered import refines *how* Plan 01 §1's two named mechanisms get
used (filter-repo, scoped, multiple passes) rather than contradicting it, but
it does change what Plan 01 §3's "land each first under a temporary
`gateway/_migration/` prefix" means in practice — the prefix holds a
domain-scoped slice per plan, not the entirety of GLC in one landing. Plan 01
itself doesn't need to change (it never committed to "all at once"), but if
you approve the checkbox above, Plan 01 §1/§3 should get a one-line
cross-reference to this section so a reader of Plan 01 alone isn't misled.

*Only after* the (now path-filtered) import does this plan re-architect the
domains it brought in — shared platform infrastructure (config, DB/
migration primitives, HTTP clients, telemetry, readiness), security/policy,
and audit/control — behind new Gateway-owned interfaces (Work Packages B–D).
The LLM provider and chat implementation are not imported by this plan at
all under the recommended option; Plan 04 imports and moves/rewrites that
code when it runs.

So: **import only platform/security/audit/control now (with full history for
those paths), re-architect them now, leave providers/chat untouched and
unimported until Plan 04 does its own scoped import.** The point of doing it
in two steps is still that Plan 04's migration would otherwise have to build
LLM/chat on top of foundations (config, DB, policy, audit) that don't exist
yet in their new form — moving those foundations first means Plan 04
migrates onto stable ground instead of creating a second set of globals (see
"Why this comes before model providers" below).

## Why this comes before model providers

Profiles, providers, channels, and chat all depend on configuration, databases,
policy, audit, security, and lifecycle behavior. Moving those foundations first
prevents the later LLM migration from creating a second set of globals.

## Decisions required before implementation



### 1. Database layout

GLC currently uses separate SQLite responsibilities for gateway calls, audit,
budgets, cache, pairing, and channel state.

Concretely, that's several independent SQLite files/connections today:
`glc_v5/glc/db.py` (the call ledger, `~/.glc/gateway.sqlite`),
`glc_v5/glc/audit/store.py` (append-only audit log with its own
`glc_v5/glc/audit/schema.sql`, `~/.glc/audit.sqlite`), plus whatever
`glc_v5/glc/economics/budget.py`, `glc_v5/glc/cache/`, and
`glc_v5/glc/security/pairing.py` each maintain for budgets, semantic cache,
and pairing codes. Nothing today merges these into one schema — this
decision is about whether that stays true after the move.

Proposed default: keep separate domain repositories and schemas. Share only
connection/migration primitives. Do not merge the data into one mega-schema.
Relocate every one of these SQLite files into the repo's `Database/` folder
as part of this move — they do not stay at `~/.glc/` or get "maintained in
place" inside `glc/` subpackages once this plan touches them. **Confirmed:
keep them unmerged — separate files/schemas are easier to write and
maintain than a shared one — but do relocate each into its own place under**
`Database/` **rather than leaving them scattered.**

- **Approve domain-owned repositories** means: each of ledger/audit/budget/
cache/pairing keeps its own table(s) and its own repository class after the
move; only the boilerplate for opening a connection and running migrations
is shared code. Benefit: a bug or schema change in budgets can't corrupt
audit data, because they're physically separate files/tables. Cost: you
can't do one SQL join across, say, ledger calls and audit entries — you'd
query each store and combine the results in Python. Regardless of which
option below is picked, the resulting file(s) live under `Database/`, not
under `~/.glc/` or a `glc/<domain>/` package directory.
- **Intentionally consolidate selected databases** means picking specific
pairs (e.g. ledger + audit, since both are per-call records) to merge into
one schema for joinability. **Not needed: cross-domain joins over separate
SQLite files don't require a merged schema —** `ATTACH DATABASE` **(or an
application-level join over two query results) gets the same answer without
coupling the schemas together.** Reach for that when a real cross-domain
query is actually needed, rather than merging schemas pre-emptively now.
- **Audit table necessity before porting anything.** Before either option
above is executed, go through each existing table in
`db.py`/`audit/store.py`/`economics/budget.py`/`cache/`/`security/pairing.py` and confirm it's still read or written by live code. A table nothing queries or inserts into anymore gets dropped during the move instead of carried forward as-is — this move is the natural checkpoint to do that audit, since every schema is already being touched.

- [x] Approve domain-owned repositories (confirmed: keep separate, don't
  merge, for easier writing/maintenance).
- [ ] Intentionally consolidate selected databases; list them below.
- [x] Approve dead-table audit as a precondition of this work package.

Database files move to `Database/` as part of this plan, resolving Plan 01
Work Package F in favor of that location (GLC's ledger and audit SQLite
files currently live at `~/.glc/`).

Moving the files is not enough on its own — the code that decides *where*
each store writes has to be updated in the same change, or the relocation
is cosmetic. Per `migration/baseline/decisions.md`'s Work Package F record,
the exact lines are `glc_v5/glc/db.py:19`
(`DB_PATH = os.getenv("GLC_GATEWAY_DB", str(DEFAULT_DIR / "gateway.sqlite"))`)
and `glc_v5/glc/audit/store.py:28`
(`os.getenv("GLC_AUDIT_DB", str(DEFAULT_DIR / "audit.sqlite"))`), both
resolved against `DEFAULT_DIR = Path(os.path.expanduser("~/.glc"))`. Read
both files in full before changing them, not just these two lines — they're
the authoritative source for how storage is wired (connection setup,
migration bootstrapping, any other reads of `DEFAULT_DIR`), so this is worth
treating as required reading, not a find-and-replace on a path string.

**Verify:** Plan 01's Work Package F is already decided —
`migration/baseline/decisions.md` records which option was picked (relocate
to `Database/sqlite/`). The check for Plan 03 having followed through is
functional, not just textual: a fresh run must stop creating
`~/.glc/gateway.sqlite` and `~/.glc/audit.sqlite` entirely, with
`Database/sqlite/` gaining the equivalent files instead.

### 2. Failure policy

GLC currently boots many optional capabilities fail-soft, while malformed
budget configuration is surfaced because silently disabling a ceiling is
dangerous. **Revised per feedback: GLC moves from fail-soft to fail-fast —
across the board, not just for budgets.** If a dependency is broken or
missing, the process should refuse to start rather than come up in a
degraded state and fail requests (or silently under-perform) later. (Fixing
the budget-config path itself is separately scoped, not this decision — this
is only about the fail-soft/fail-fast boot policy.)

Proposed default (fail-fast, no degraded-start path). Per-dependency, so
this is decided once and checkable, not left as a vague "everything
fails hard now":


| Dependency                                              | Today                      | Under this plan                                                                                                                                                      |
| ------------------------------------------------------- | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `policy.yaml` (`glc_v5/glc/policy/`)                    | fail-hard already          | stays fail-hard                                                                                                                                                      |
| `budgets.yaml` (`glc_v5/glc/economics/`)                | fail-soft; boots with budget enforcement off | **fail-hard in Gateway** — malformed budget configuration prevents LLM-service startup                                                                                                    |
| Semantic cache backend (`glc_v5/glc/cache/semantic.py`) | fail-soft, serves uncached | **fail-hard in Gateway** — the persistent SQLite backend is checked at startup, and request-time database failures propagate instead of silently serving uncached     |
| OTel export (`glc_v5/glc/telemetry/otel.py`)            | fail-soft, serves untraced | **fail-hard** — an unreachable collector blocks boot; there is no "serve without tracing" mode after this plan                                                       |


**Porting methodology (how fail-soft actually gets converted, and how you
know you got every instance):**

1. Grep `glc_v5/glc/` for every `try`/`except` around a startup-time
  dependency check (cache connect, OTel exporter init, any other
   integration touched in `main.py`'s boot sequence) and list them — this
   is the actual inventory of "fail-soft sites," not just the two named
   above; there may be others once you look.
2. Convert one site at a time, not all at once. For each: write the
  "process refuses to start when this is broken" test *before* changing
   the code (it should fail against today's fail-soft behavior), then flip
   the `except` to re-raise/exit instead of logging-and-continuing, then
   confirm the new test passes.
3. Re-run the full existing GLC suite (563 tests, per the baseline) after
  *each* individual conversion, not just at the end — a fail-soft path
   converted to fail-hard can break an existing test that was relying on
   degraded-but-running behavior, and you want that attributed to the one
   site you just changed, not discovered later mixed in with five other
   changes.
4. When step 1's inventory is fully converted and step 3 stays green, the
  table above should be the complete list of dependencies with no
   unlisted stragglers — that completeness, not just "we fixed cache and
   telemetry," is what "ported well" means here.

- Report the specific failing dependency through structured startup
errors/logs — the process still needs to say *which* check failed (cache
unreachable vs. telemetry unreachable vs. bad `policy.yaml`) so a fail-fast
crash is diagnosable in one read, not just "startup failed." (Structured,
machine-parseable startup errors are also what a future automated
log-reader — human or LLM — would need to flag anomalies without someone
grepping by hand; building that reader is out of scope for this plan, but
the structured-log requirement here is what would make it possible later.)

- [x] Approve fail-fast policy (implemented), per the table: cache
  and OTel export join config/budgets as hard-fail dependencies, with
  no degraded-start path for any of them.
- [ ] List any domain that is a deliberate exception to fail-fast, if any exist.

**How you'll verify this landed:** a test that starts GLC with a corrupted
`policy.yaml` or `budgets.yaml` and asserts the process refuses to start; a
second test that breaks only the cache backend, and a third that breaks
only the telemetry export target, each asserting the process refuses to
start and the startup error names the specific broken dependency (not a
generic failure, and not "starts anyway"). These four tests are also the
per-site tests called for in step 2 of the porting methodology above, not
an additional set.

### 3. Policy reload

Proposed default: preserve SIGHUP reload temporarily and add an authenticated
control operation that invokes the same service method.

**In plain terms:** today, someone with shell access to the box can make GLC
pick up a new `policy.yaml` without restarting the process by running
`kill -SIGHUP <pid>`. The proposal is to (1) keep that working exactly as-is
for now, and (2) *additionally* expose an HTTP endpoint (e.g.
`/v1/control/reload-policy`, protected by the same install-token check as
the other control routes) that does the identical reload — so anything that
can make an authenticated HTTP call (not just something with shell/process
access to the host) can also trigger a reload. Both paths end up calling the
same underlying `reload_engine()` function, so there's one reload
implementation with two ways to trigger it.

**Knock-on effects of adding the API path:**

- **Who can trigger a reload gets wider.** Today it's "whoever can send a
signal to this specific process" (shell/process access to the host).
After this, it's "whoever holds a valid install token" — the same
population that can already hit `/v1/control/kill` and the other control
routes, so this isn't a new trust boundary, but it is a new *capability*
granted to that existing population, and a bug in the new route is now
remotely reachable in a way `SIGHUP` never was.
- **It needs to be logged like the other control actions.** `/v1/control/ kill`, `/pair`, etc. going through an authenticated route means they're
the kind of action this plan's audit domain (§4/Work Package D) would
expect to see in the audit log; a reload triggered over HTTP should land
in that same log. A reload triggered by `SIGHUP` today has no such
record — worth deciding explicitly whether that asymmetry (API reloads
audited, signal reloads not) is acceptable or whether `SIGHUP` should log
too, once both paths exist.
- **Signal-handling collision, once GLC and Gateway share a process.**
Checked in this repo: `gateway/main.py` today runs bare
`uvicorn.run("main:app", ...)` with no signal handling of its own, and no
process manager (gunicorn, supervisor) sits in front of it — so there is
no known conflict with GLC's `SIGHUP` handler *today*. But this is a
"verify before keeping the signal path" item, not a settled fact: if
Gateway later runs under a process supervisor that reserves `SIGHUP` for
its own reload semantics (common for gunicorn workers, for example),
GLC's handler and the supervisor's handler would compete for the same
signal once they're one process. Re-check this at implementation time,
not just now.

Full mechanics below:

Today `glc_v5/glc/main.py`'s `_install_sighup_reload()` function registers a
`signal.signal(signal.SIGHUP, _handler)` handler whose body calls
`reload_engine()` (imported from `glc.policy`) — sending `SIGHUP` to the
running GLC process reloads `glc_v5/glc/policy/policy.yaml` without a
restart (Windows has no `SIGHUP`, so this is already a documented no-op
there per the function's own docstring). `glc_v5/glc/routes/control.py`
already has an authenticated control surface (`/v1/control/kill`, `/pair`,
`/pair/confirm`, `/presence`, gated by the install token) that a reload
endpoint would join.

- **Preserve SIGHUP plus API reload**: keep sending `SIGHUP` for scripted/
terminal use, and add e.g. `/v1/control/reload-policy` behind the same
install-token check as the existing control routes, calling the identical
`reload_engine` function underneath. Two ways in, one code path.
- **API-only reload**: drop `SIGHUP` handling, keep only the authenticated
endpoint. Simpler surface, but breaks any script that currently sends the
signal directly.
- **Restart-only configuration**: no live reload at all — a policy change
requires restarting the process. Simplest, but means a config typo isn't
caught until the next full restart, and reload can no longer be
automated cheaply.

- [x] Preserve SIGHUP plus API reload.
- [ ] API-only reload.
- [ ] Restart-only configuration.

**How you'll verify this landed:** whichever mechanism is kept, a test edits
`policy.yaml` on disk, triggers the chosen reload path, and asserts the
running process's policy decisions reflect the new file — without a
process restart.

### 4. Legacy GLC import visibility

**Revised per feedback, round 2: the previous round's "no compatibility-
adapter layer" default still stands for internal Python imports — but the
new comment reads as a check on quality, not a reopening of that default:
wherever delegation code does exist (Work Package E's route handlers, or
any exception granted under the second checkbox below), it must be real,
fully-implemented code with its own genuine imports of the new Gateway
module — not a disposable ad hoc wrapper function bolted onto the old
route file.** That distinction wasn't stated explicitly before, so it's
worth being explicit now rather than assuming which reading was meant:

- Once a domain's logic (e.g. `glc_v5/glc/audit/store.py`) is ported into a
Gateway-owned module, the old `glc.audit.store` module itself is
retired — deleted, not turned into a thin delegating shim that exists
solely so old imports keep working. Anything that used to `import glc.audit` gets updated at the same time to import the new Gateway
module directly.
- Where delegation *is* required — Work Package E's route handlers, which
by definition keep calling into new-Gateway-owned logic from an
old-numbered route path — that handler code is a proper, fully-built
module with real imports of the new service, held to the same quality
bar as any other production code in this plan. "No ad hoc wrappers"
means: not a five-line function improvised to unblock a contract test,
written once and never revisited.

If this reading is wrong and the intent was actually to allow standing
internal compatibility-adapter modules (not just route-level delegation) as
long as they're well-built — that's a different, larger default than what's
written above, and worth saying explicitly rather than leaving this plan to
guess a second time.

The one-way rule still holds and is actually simpler under this default:
new Gateway code never imports `glc.*` (nothing to import — it's gone), and
old `glc.*` modules don't stick around to be imported *by* anything else
either. Only two things still legitimately reference "old GLC" after this
plan, and neither is a compatibility-adapter module:

- **Work Package A's standalone copy** — the original GLC submodule/service
kept runnable *outside* the merged codebase, for rollback. That's a
separate deployable artifact, not in-tree wrapper code, so retiring
in-tree `glc.*` modules doesn't touch it.
- **Work Package E's route-level delegation** — old HTTP route *paths*
(e.g. `/v1/control/kill`) stay reachable and preserve their existing
status codes/error shapes, but their handler bodies call the new
Gateway service directly; the old Python module that used to contain that
handler's logic does not need to keep existing as a separate importable
module once the route file itself calls the new service.

- [x] Approve: retire old `glc.*` modules outright once ported (no
  compatibility adapters).
- [ ] Specify exceptions below, if any module genuinely needs a transition
  period (e.g. an external caller outside this repo that imports `glc.*`
  directly and can't be updated in the same change).

**How you'll verify this landed:** Work Package A below calls for
"dependency-direction tests before reorganizing code" — extend that check
so it fails not just on new-code-imports-legacy, but also on the presence
of any retired `glc.*` module path once its Gateway-owned replacement
exists (e.g. `glc.audit.store` should no longer be importable at all, not
just "not imported by new code"). It should pass with zero exceptions
unless you explicitly listed one above.

## Work packages



### A. Accepted snapshot import

- Import only the paths this plan needs (platform config/DB/HTTP/telemetry,
security/policy, audit/control, and their tests) as a tracked snapshot. The
pre-import per-file history requirement was waived after implementation.
- Treat the Gateway landing commits as the history boundary; no history
rewrite or re-import is required.
- Keep the original submodule and standalone service runnable.
- Add dependency-direction tests before reorganizing code.



### B. Platform infrastructure

- Move configuration resolution. *(Today:* `glc_v5/glc/config.py` *— e.g.*
`get_or_create_install_token()`*, used by* `routes/control.py`*'s auth check.)*
- Introduce shared database and migration primitives. *(The common
connection/migration boilerplate that decision #1 says stays shared even
while ledger/audit/budget/cache/pairing keep separate schemas.)*
- Introduce lifespan-managed outbound HTTP clients. *(GLC's provider calls —*
`glc_v5/glc/providers.py`*,* `direct_providers.py` *— currently open their own
HTTP clients per call/provider; this centralizes them so Plan 04 can reuse
one client per provider across requests instead of recreating one each
time, which is also this plan's platform-level half of Plan 04's later
"reuse lifespan-managed HTTP clients" hardening step.)*
- Move telemetry initialization and shutdown. *(Today:*
`glc_v5/glc/telemetry/otel.py`*, wired up inside* `glc_v5/glc/main.py`*.)*
- Add startup dependency checks and structured startup errors. *(This is
where decision #2's fail-fast policy actually gets implemented — one place
that asks every subsystem "are you healthy?" before the process finishes
starting, and refuses to start naming whichever one said no.)*

**How you'll know Work Package B is done:** GLC's existing test suite (563
tests per the roadmap's verified baseline) still passes against the moved
platform code; deliberately breaking the cache backend, and separately the
telemetry export target, each cause the process to refuse to start with a
startup error naming that specific dependency — not a degraded-but-running
process.

### C. Security and policy

- Move trust classification, allowlists, pairing, rate limits, and SSRF
rules. *(Today:* `glc_v5/glc/security/trust_level.py`*,* `allowlists.py`*,*
`pairing.py`*,* `rate_limits.py`*,* `ssrf.py` *— five files, ~650 lines total.
SSRF rules matter here because channel webhooks/outbound calls must not be
tricked into hitting internal-only addresses; there's already a*
`glc_v5/tests/test_ssrf_guard.py` *characterizing this today.)*
- Move policy schemas, configuration, evaluation, and reload behavior.
*(Today:* `glc_v5/glc/policy/engine.py`*,* `schemas.py`*,* `policy.yaml` *— this
is what decision #3 above reloads.)*
- Keep channel/vendor signature verification within its integration package.
*(E.g. Twilio's webhook signature check stays inside*
`glc_v5/glc/channels/catalogue/twilio_sms/webhook.py`*'s own package, not
hoisted into this shared security module — each vendor's signature scheme
is that vendor's own concern, not a generic security primitive.)*
- Add authorization and refusal characterization tests. *(Tests that pin
down today's exact 401/403/429-style refusal behavior before it moves, so
a behavior change during the move is caught by a failing test rather than
discovered later.)*

**How you'll know Work Package C is done:** the existing
`glc_v5/tests/test_ssrf_guard.py` (and the rest of GLC's security tests)
pass unchanged against the moved code; a request that trips an allowlist,
rate limit, or SSRF rule today produces the identical refusal after the
move.

### D. Audit and control

- Move audit storage and query interfaces. *(Today:*
`glc_v5/glc/audit/store.py` *plus its* `schema.sql` *— an append-only log,
currently at* `~/.glc/audit.sqlite`*, autocommit per insert so nothing is
lost mid-batch.)*
- Move control operations and routes. *(Today:*
`glc_v5/glc/routes/control.py` *—* `/v1/control/kill`*,* `/pair`*,*
`/pair/confirm`*,* `/presence`*, each gated by the install token from*
`glc.config.get_or_create_install_token()`*; the kill endpoint additionally
binds to* `127.0.0.1` *only, enforced in the route itself.)*
- Define kill/presence/pairing behavior within the unified Gateway lifecycle.
*(Once GLC's process and Gateway's process become one process, "kill" can
no longer mean "this whole process exits" if Gateway also owns ingestion
and the shell — decide what kill actually does in the merged process.)*
- Ensure audit failures have an explicit fail-open or fail-closed policy.
*(If the audit database write fails, does the LLM call that triggered it
still succeed (fail-open, but now unaudited) or does the call itself fail
(fail-closed, but now availability depends on the audit store)? This must
be a deliberate choice, not whatever falls out of unhandled exception
behavior today.)*

**How you'll know Work Package D is done:** the 127.0.0.1-only bind on the
kill endpoint is preserved and tested (a request from a non-local address
must still be rejected); a test that fails the audit write and asserts the
documented fail-open/fail-closed behavior, not an unhandled exception.

### E. Compatibility delegation

- Make selected old GLC endpoints delegate to the new Gateway-owned services.
*(E.g.* `glc_v5/glc/routes/control.py`*'s routes, still reachable at their
current paths, but their handler bodies now call the new Gateway-owned
control service instead of the old in-file logic.)*
- Preserve old errors, status codes, and environment variables. *(A request
that got a 403 "install token mismatch" today must still get exactly that
after delegation — not a generic 500 because the new service raises a
different exception type.)*
- Do not proxy in-process calls over HTTP when a direct service adapter is
sufficient. *(If GLC's routes and the new Gateway service end up in the
same process, the old route should call the new service's Python method
directly — it must not make an HTTP request to its own process's own port
just to reach code that's already loaded in memory.)*

**How you'll know Work Package E is done:** the preserved GLC contract
tests from Plan 01 (`migration/baseline/contracts/glc-openapi.json` and its
fixtures) pass against the delegating routes; `grep` for `httpx`/`requests`
calls targeting `127.0.0.1:8111` or the Gateway's own port from inside
Gateway's own process turns up nothing.

## Explicitly out of scope

- Moving model providers.
- Splitting the chat route.
- Moving channels or voice.
- Moving ingestion.
- Database engine replacement.



## Exit gate

- Gateway owns lifecycle, configuration, security, policy, audit, and control.
- New modules do not import legacy `glc.*` implementations, and retired
`glc.*` modules are gone (not kept alive as compatibility wrappers).
- Old routes pass preserved contract tests through direct delegation to
Gateway-owned services (Work Package E) — not through a legacy Python
module.
- Fail-fast startup, shutdown, and security failure behavior are tested —
including that a broken optional dependency (cache, telemetry) now stops
startup rather than degrading it.
- GLC standalone remains runnable as rollback protection (the separate
submodule/service copy from Work Package A, not an in-tree adapter).

**Exit gate result: PASS.** The semantic cache is now a persistent, tenant-scoped SQLite domain store at
`Database/sqlite/semantic_cache.sqlite`; startup performs a named, writable health check; cache reads and
writes fail closed; and cache SQLite work is kept off the async event loop. The focused Plan 03/LLM checks
pass (23 tests), `mypy --strict` is clean (68 source files), and the full Gateway suite has 91 passing tests.
Its sole remaining failure is the previously documented, unrelated stale generated TypeScript schema.



## Aryaman's comments

Round 1 (import scope, DB location, dead-table audit, fail-fast vs.
fail-soft, SIGHUP/reload explanation, no legacy compatibility adapters)
addressed inline above on 2026-09-15.

Round 2, addressed inline above on 2026-09-16: the Goal section's "import
all of GLC verbatim" was walked back to a proposed path-filtered import
(recommended, left unchecked pending explicit confirmation since it's a new
mechanism — `git filter-repo`, multiple scoped passes — not something
approved yet; two alternatives are listed and rejected-by-default, and if
confirmed it touches Plan 01 §1/§3 and needs a one-line cross-reference
added there); the domain-owned-repositories checkbox under decision #1 is
now checked, since "don't merge" was an explicit yes; the DB-consolidation
option now notes `ATTACH DATABASE`
as the lower-coupling way to get cross-domain joins later; the DB-relocation
decision now names the exact `db.py`/`audit/store.py` lines that need
updating alongside the file move; the fail-fast decision now has a
per-dependency table plus a step-by-step porting/verification methodology
instead of just two examples; the policy-reload decision now spells out
knock-on effects (who gains reload capability, audit-log asymmetry between
the two paths, and a checked-not-assumed note on `SIGHUP` handler
collisions once GLC and Gateway share a process); and the legacy-import
decision now distinguishes "no standing internal compatibility-adapter
modules" from "Work Package E's route-level delegation code must itself be
genuine, fully-built code" — flagged as a guess at intent rather than a
confirmed reading, since the comment could also mean adapters are allowed
generally as long as they're well-built.

Add further database, security, failure-mode, policy, and control
requirements here.
