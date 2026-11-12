# Plan 07 — Runtime Cutover and Legacy Removal

## Goal

Make the unified Gateway the canonical runtime, migrate every known caller,
observe the compatibility boundary, and remove the old GLC and ingestion
submodules only when they are no longer required.

## Decisions required before implementation

### 1. Final process model

Proposed default: in-process domains on 8000; separate only long-running or
failure-sensitive workers that have a documented operational reason.

Today there are two processes: Gateway on port 8000
(`gateway/main.py`'s `uvicorn.run(..., port=8000)`) and GLC standalone on
port 8111 (`glc_v5/glc/main.py`: `PORT = int(os.getenv("GLC_PORT", "8111"))`).
By this point in the program, GLC's code has already moved in-process
(Plan 03/04) and ingestion has already moved in-process (Plan 06) — this
decision is the final word on whether *anything* still runs as a separate
process once all that's done, and if so, what and why.

- **One Gateway process on port 8000 plus explicitly configured workers**:
  the default outcome of everything Plans 02–06 built — chat, ingestion,
  security/audit/control all answer from one process; only the channel
  workers Plan 05 decision #1 identified as needing isolation (long
  pollers, native-dependency-heavy adapters) run separately, and only
  because that was decided explicitly, not by default.
- **Separate LLM and ingestion processes behind Gateway routing**: undoes
  the in-process injection this whole program built (Plan 02 decision #3,
  Plan 04 decision #2, Plan 06 decision #2) in favor of network calls
  between Gateway and each domain — a real reversal of direction, not a
  minor variant.

- [x] One Gateway process on port 8000 plus explicitly configured workers.
- [ ] Separate LLM and ingestion processes behind Gateway routing.
- [ ] Another deployment model described below.

**Decided 2026-09-28.** `gateway/config/services.yaml` is the single
registry: `gateway` (8000, required), `glc_legacy` (8111, optional), and any
explicitly enabled workers (`agent_runtime` on 8113, `telegram_worker` on
8121, disabled by default). Port 8000 stays a deliberate, permanent
exception to the 81xx reserved block — it's the well-known, already-
documented entry point this decision's port note anticipated.

**Port note carried from Plan 02 decision #4:** every *new* service the
registry gains from Plan 02 onward is assigned from a reserved, out-of-the-
way port block (e.g. `81xx`) specifically so it can't collide with other
software on the machine. Gateway's port 8000 and GLC's legacy port 8111
predate that convention and were both explicitly out of scope for Plan 02 to
touch. This decision is the place to decide whether to also move Gateway's
own port into the reserved block for consistency, or to keep 8000 as a
deliberate, permanent exception (e.g. because it's already a well-known,
documented entry point). Either is fine — just make it an explicit choice
here rather than leaving 8000 as "whatever it happened to be."

**How you'll verify this landed:** `ps`/process listing on a running
deployment shows exactly the processes this decision named — one Gateway
process plus only the specifically-approved workers, nothing extra
listening on its own port "just because it always has."

### 2. Port 8111 transition

Proposed default: keep a temporary compatibility listener or proxy only while
observed callers remain. Instrument it, warn on use, then remove it.

Grounding — the actual known callers of port 8111 today (per Plan 01's
caller inventory, `migration/baseline/caller-inventory.md`, and this repo's
own grep): `ingestion-pipeline/merged-ingestion/src/ingestion/runner.py`
(defaults to it, overridable via `GLC_BASE_URL`), `glc_v5/daemon/install.sh`,
`glc_v5/glc/cli.py`, `glc_v5/glc/client.py`, and several channel dev/demo
scripts under `glc_v5/glc/channels/catalogue/*` (Discord, Twilio SMS, Twilio
Voice, Telegram, WhatsApp). Every one of these should already have been
migrated to the in-process path by Plan 04/06/07 Work Package B before this
decision's cutover actually removes anything — this decision is about *how
long* to keep 8111 answering for any caller that was missed.

- **Approve observed-usage cutover**: keep a compatibility listener up,
  logging who connects, until real traffic against it is zero for an
  agreed window — then remove it. Safest, since it's driven by evidence
  rather than a guess.
- **Remove 8111 on a fixed release/date**: simpler to plan around, but risks
  breaking a caller that wasn't fully migrated in time.
- **Keep 8111 permanently as an alias**: no cutover risk at all, but the old
  port (and whatever ran on it) becomes permanent surface area to maintain.

- [x] Approve observed-usage cutover.
- [ ] Remove 8111 on a fixed release/date.
- [ ] Keep 8111 permanently as an alias.

**Decided 2026-09-28, with one modification to the proposed default.**
`gateway/src/gateway/compatibility/legacy_listener.py` is an optional,
explicitly-started proxy (disabled unless `glc_legacy` is enabled in the
registry) that forwards HTTP/SSE/WebSocket traffic to Gateway and logs only
connection metadata — timestamp, protocol, source IP — never paths, headers,
or bodies. `gateway/scripts/legacy_usage_report.py` turns those logs into
daily connection counts, which is the observed-usage mechanism this decision
asks for. **Modification:** shipping Gateway is not gated on a fixed
observation window running to zero first, per the user's 2026-09-25 scope
call recorded in `migration/plan-07-cutover-status.md` — the previous
14-day-window-before-ship requirement was this plan's own proposed default,
not something the user had asked for, and was withdrawn. The mechanism to
run an observation window and act on it still exists and can be used
opportunistically post-ship whenever 8111 usage needs to be measured before
turning it off.

**How you'll verify this landed:** the observation window's logs (Work
Package C) show zero connections to 8111 immediately before it's removed;
after removal, every caller named in `migration/baseline/caller-inventory.md`
still functions using its migrated, in-process or Gateway-port path.

### 3. Legacy Python imports

Proposed default: retain a thin `glc.client` compatibility package only long
enough for external Python callers to migrate; prohibit it in Gateway-owned
production code immediately.

**Correction to an earlier assumption here:** this section previously said
`glc.client.LLM` was "being formalized into `gateway/sdk/`, per Plan 04 Work
Package F." That's not what happened — Plan 04 decision #5 **deferred**
building any SDK (no external caller existed to justify one), so Work
Package F never ran and no `gateway/sdk/` package exists. Separately, Plan
06 gave ingestion — the only in-repo consumer of `glc_v5/glc/client.py`
outside `glc_v5`'s own tests — its own Gateway-owned HTTP client instead of
continuing to import it (`06-ingestion-domain-migration.md` decision #2,
`06a-implementation-handoff.md` §0.1). So by the time this plan runs,
`glc_v5/glc/client.py` should already have **zero in-repo importers**; the
file itself is untouched and still exists (neither Plan 04 nor Plan 06
deletes it), just unused internally. This decision is therefore not about a
shim that wraps a new SDK — there is no SDK — it's about whether to keep the
orphaned, still-working `glc_v5/glc/client.py` package around a while longer
for any *external* (out-of-repo) Python caller that might have appeared
since Plan 04 deferred that question, or remove it immediately since none
was known to exist as of Plan 04. Gateway's own code was never allowed to
import it in the first place (Plan 03 decision #4's one-way dependency
rule) — that part of the original text still holds.

- [x] Approve temporary Python compatibility.
- [ ] Remove all `glc.*` imports at the HTTP cutover.

**Decided 2026-09-28.** `glc_v5/glc/client.py` is retained, untouched, for
any external (out-of-repo) Python caller — none is known to exist, but none
has been ruled out either. Gateway's own code has zero `glc.*` imports
(`grep -rn "^import glc\|^from glc" gateway/src` — zero hits) and
`gateway/src/gateway/ingestion/` (the only former in-repo importer) now uses
its own `GatewayHTTPClient` instead. Revisit removing `glc_v5/glc/client.py`
itself if an external caller inventory is ever taken and comes back empty —
none is planned as part of this plan.

**How you'll verify this landed:** `grep -rn "^import glc\|^from glc"
gateway/src` turns up nothing (Gateway's own code never imported it, per
Plan 03); a repo-wide `grep -rn "glc\.client\|glc_v5" --include="*.py"`
outside `glc_v5/` itself turns up nothing once Plan 06's ingestion caller is
gone (confirmed as of this writing: ingestion was the only in-repo
importer). `glc_v5/glc/client.py` itself is removed — if this decision opts
to remove it at all, rather than retain it — only after
`migration/baseline/caller-inventory.md`'s Python-import callers have all
been re-verified as zero; there is no `gateway/sdk/` to switch them to, and
none is planned.

### 4. Archival policy

This decides the final fate of the `glc_v5` and `ingestion-pipeline`
submodules themselves — not their code (which by now lives inside Gateway
per Plans 03/04/06), but the standalone repositories that once ran it.

- **Remove submodules after their replacements are pushed and tagged**: the
  `.gitmodules` entries and submodule references disappear from this repo
  entirely once the migrated code is proven and tagged; the original repos
  still exist wherever they're hosted, just no longer referenced here.
- **Retain read-only archived directories in the parent repository**: keep
  a snapshot of the old code physically present (e.g. under an `archive/`
  path) for reference, but no longer wired up as a submodule or runnable.
- **Retain only external source repositories/tags**: don't keep anything in
  this repo at all — rely on the original repos' own history/tags as the
  record, reachable only by going to look at them separately.

- [x] Remove submodules after their replacements are pushed and tagged.
- [ ] Retain read-only archived directories in the parent repository.
- [ ] Retain only external source repositories/tags.

**Decided 2026-09-28.** The migrated replacement code was committed and
tagged `plan-07-pre-legacy-removal` first; `.gitmodules` and the `glc_v5`/
`ingestion-pipeline` working directories were then removed from this repo in
a separate, later commit. Both original repositories still exist at their
hosted URLs (`https://github.com/Aryamanchandak/glc_v5.git` and
`git@github.com:Aryamanchandak/AI-OS-Ingestion-Pipeline.git`, per the former
`.gitmodules`) — this repo simply stops referencing them. `gateway/tests/test_standalone_bootstrap.py`
proved before removal that Gateway boots with neither sibling directory
present, so this wasn't a leap of faith.

**How you'll verify this landed:** `git submodule status` no longer lists
`glc_v5`/`ingestion-pipeline` (if removal was chosen), and whatever
retention option was picked is actually reachable the way this decision
describes — e.g. an `archive/` path exists and is readable, not just
promised.

## Work packages

### A. Make service registry authoritative

- Resolve Gateway and worker ports from one validated configuration. *(The
  `config/services.yaml` registry built in Plan 02 decision #4 becomes the
  single source of truth — no code anywhere still hard-codes `8000` or
  `8111`.)*
- Update launchd, systemd, Windows, Docker, demo, and local scripts.
  *(Concretely includes `glc_v5/daemon/install.sh`, which currently installs
  GLC as its own daemon on 8111 — it needs to reflect whatever the final
  process model from decision #1 is.)*
- Remove copied production literals for port 8111. *(Every hard-coded
  `8111`/`http://127.0.0.1:8111` found in Plan 01's caller inventory —
  `glc_v5/glc/cli.py`, `glc_v5/glc/client.py`, the channel dev scripts, etc.
  — gets replaced with a registry lookup.)*
- Add authenticated service-health diagnostics.

**How you'll know Work Package A is done:** `grep -rn "8111" --include="*.py"
--include="*.sh"` across the repo (excluding archived/legacy directories per
decision #4) turns up nothing left uncovered by the registry.

### B. Migrate callers

- Update ingestion, S16/agent runtime, scripts, shell, tests, desktop tools,
  and documentation.
- Replace direct `glc.*` imports with supported Gateway clients/contracts.
- Record owner and completion evidence for every Plan 01 caller. *(Every row
  in `migration/baseline/caller-inventory.md` gets a "migrated" mark and
  evidence — a commit, a test, a doc update — before this plan's exit gate;
  "classified" from Plan 01 becomes "resolved" here.)*

**How you'll know Work Package B is done:** every caller row from Plan 01's
inventory that was marked "active" now points at a supported Gateway
contract, with evidence linked; none are left in "classified but not yet
migrated" state.

### C. Run compatibility observation

- Instrument legacy HTTP and Python compatibility use without logging content
  or secrets. *(Log "something connected to port 8111" and who/when, never
  the request/response bodies — those could contain chat prompts or
  credentials.)*
- Exercise HTTP, SSE, and WebSocket behavior through any temporary proxy.
- Define the no-usage observation window.
- Publish deprecation messages and final cutover instructions.

**How you'll know Work Package C is done:** a report exists showing the
observation window's connection counts trending to zero, with a specific
date/commit where they hit zero — that's the evidence decision #2's
observed-usage cutover actually relies on.

### D. Operational readiness

- Cold start, restart, shutdown, and crash recovery.
- Provider/channel worker isolation. *(Re-proving Plan 05 Work Package C's
  "a broken optional adapter cannot prevent unrelated Gateway domains from
  starting," now against the final, fully-merged process.)*
- Health/readiness behavior under partial failure.
- Concurrent budget, audit, cache, and ingestion database activity. *(A
  combined load test — chat traffic hitting budget/audit/cache at the same
  time ingestion is writing to its own database — proving Plan 04's atomic
  budget reservation and Plan 06's database boundary both hold up together,
  not just individually.)*
- Backup/restore and configuration rollback.
- Secret redaction and least-privilege review.

**How you'll know Work Package D is done:** each bullet above has a
corresponding test or drill that was actually run once, with its result
recorded — not just asserted as a checklist item.

### E. Remove legacy boundaries

- Remove the 8111 listener after its approved exit condition.
- Remove `glc.client` compatibility after its caller inventory reaches zero.
- Remove starts of `glc.main`. *(`glc_v5/glc/main.py`'s own
  `if __name__ == "__main__": uvicorn.run("glc.main:app", ...)` — once
  nothing starts this file directly anymore, remove the entry point itself,
  not just stop calling it.)*
- Remove obsolete environment aliases. *(`GLC_BASE_URL`, `GLC_PORT`,
  `GLC_GATEWAY_DB`, `GLC_AUDIT_DB` — once every reader of these has moved to
  the registry/config system, the aliases themselves go, not just their
  usages.)*
- Remove GLC and ingestion submodules and update `.gitmodules` deliberately.
- Archive/tag source repositories according to decision 4.
- Replace legacy documentation with Gateway-domain documentation.

**How you'll know this whole plan is done — the final check:** every item
in "Required final verification" below passes, and a fresh clone of the
repository, following only `gateway/README.md`'s (by-then-updated)
instructions, builds, tests, and runs with no reference anywhere to
`glc_v5`, `ingestion-pipeline`, `glc.main`, or port 8111.

## Required final verification

- Gateway, ingestion, GLC-preserved contract, frontend, type, and lint suites.
- OpenAPI comparison with intentional differences approved.
- Chat, structured output, embed, batch, SSE, WebSocket, webhook, STT, TTS,
  budgets, cache, audit, and ingestion end-to-end tests.
- Search proving no production dependency on `glc_v5`, the old ingestion
  package, `glc.main`, or copied port 8111.
- Fresh-machine/bootstrap test using only canonical Gateway instructions.

## Exit gate

*(Also the definition of done for ingestion Stage A item 3; see
`To Do/Ingestion Pipeline to do/A3-ui-ownership-closeout.md`.)*

- Unified Gateway is the sole documented application entry point.
- Every active caller uses a supported Gateway contract.
- Compatibility traffic is zero for the approved observation window.
- Old submodules are unnecessary for build, test, runtime, and operation.
- Replacement commits are pushed, tagged, and recoverable before deletion.
- Rollback and backup procedures have been exercised.

## Aryaman's comments

Recorded 2026-09-28, consolidating the four decisions above:

- **Final process model**: one Gateway process on port 8000, plus only the
  explicitly-enabled workers named in `gateway/config/services.yaml`. Port
  8000 stays permanently, by design, outside the 81xx reserved block.
- **Observation window**: the 8111 compatibility listener is optional
  (off unless `glc_legacy` is enabled), instrumented (connection metadata
  only), and has a usage-report script. No fixed pre-ship observation window
  is required — that was this plan's own proposed default, not a
  requirement I asked for. The tooling to run one later, before ever
  disabling 8111, still exists if needed.
- **Retirement policy**: `glc_v5` and `ingestion-pipeline` are removed as
  git submodules from this repo once their replacement code is committed
  and tagged (tag: `plan-07-pre-legacy-removal`). The original repos remain
  reachable at their own hosted URLs.
- **Legacy interface callers**: none inside this repo need to retain a
  legacy interface — ingestion and the shell both call Gateway's own
  contracts. `glc_v5/glc/client.py` is kept around, unremoved, only as a
  courtesy for any external (out-of-repo) Python caller that might still
  exist; none is known.

