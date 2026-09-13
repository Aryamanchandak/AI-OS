# Plan 01 — Baseline and Ownership Decisions

## Goal

Make the current system recoverable and define exactly what must remain
compatible before moving code. This plan changes no runtime ownership.

## Why this is first

`glc_v5` and `ingestion-pipeline` are Git submodules whose checked-out states
are ahead of the commits recorded by the parent repository. Both contain
uncommitted work, while `gateway/` is currently untracked by the parent. A
structural import now could lose history or silently omit active changes.

This plan has already been carried out. Every decision below is checked, and
the work packages produced real files under `migration/baseline/` at the AI
OS root — start at `migration/baseline/README.md`, which indexes all of it.
The additions below point each decision and work package at the specific
file that proves it happened, so you can open that file and check it
yourself instead of taking the checkbox on faith.

## Decisions required before implementation

### 1. History policy

Proposed default: preserve full history for both GLC and ingestion using a
history-aware import, then move imported paths in later commits.

- [x] Preserve full history.
- [ ] Preserve only one reviewed snapshot plus a reference to the source commit.
- [ ] Different policy for GLC and ingestion; describe it below.

**"Preserve full history" means:** when GLC's and ingestion's commits get
imported into this repo (Plan 03/06), the import brings every past commit
those two repos ever made with it — like `git subtree add` or a filtered
`git fetch` + merge — rather than a single squashed "here's the code as of
today" commit. The cost is a noisier `git log` for those paths forever; the
benefit is `git blame`/`git log -p` still work on GLC/ingestion code after
the move, the same way they do today inside each submodule.

**Verify:** `migration/baseline/repo-state.md` records the chosen history
import procedure and rollback procedure (Work Package A below) — open it to
see the exact mechanism decided on, not just that a box got checked.

### 2. Compatibility policy

Proposed default: freeze current `/v1/*` GLC routes contracts and
`/api/ingestion/*` contracts until caller migration is complete.

- [x] Preserve URLs, status codes, response bodies, SSE frames, and WebSocket
      behavior byte-for-byte where practical.
- [ ] Permit selected contract changes during migration; list them below.

**Concretely:** today GLC serves `/v1/chat`, `/v1/embed`, etc. on port 8111
(`glc_v5/glc/main.py`), and Gateway serves `/api/ingestion/*` on port 8000
(`gateway/main.py`). This decision says both surfaces must answer identically
— same status codes, same JSON shapes, same SSE byte framing — after they
move under Gateway, for as long as anything still calls them the old way.
It's what lets Plans 03/04/06 be verified by diffing against a snapshot
instead of by re-reading every route by eye.

**Verify:** `migration/baseline/contracts.md` plus
`migration/baseline/contracts/glc-openapi.json` and
`.../gateway-openapi.json` are the frozen snapshots later plans diff against.
Any future plan's OpenAPI export should match these route shapes exactly,
except for genuinely new routes.

### 3. Import landing area

Proposed default: import each repository first under a temporary
`gateway/_migration/` prefix. Do not reorganize during the import commit.

- [x] Use a temporary migration prefix.
- [ ] Import directly into final domain folders.

**Concretely:** when Plan 03 imports GLC and Plan 06 imports ingestion, the
first commit that brings each one in lands at `gateway/_migration/glc/...`
and `gateway/_migration/ingestion/...` rather than directly at
`gateway/src/gateway/llm/...` or `gateway/src/gateway/ingestion/...`. The
reorganizing move into the final folder happens as a *separate*, later
commit. This is what keeps "did the import preserve every file and its
history" and "did the reorganization keep behavior identical" as two
independently reviewable diffs instead of one giant one.

**Verify:** once Plan 03/06 land, `git log --follow` on any moved GLC/
ingestion file should show a `gateway/_migration/...` path in its history
before its final path — if a file's history starts directly at the final
path with no `_migration` stop, this decision wasn't followed for it.

### 4. Dirty working trees

- [x] Review and commit the current GLC changes in its own repository.
- [x] Review and commit the current ingestion changes in its own repository.
- [x] Decide which currently untracked root files belong in the AI OS parent.
      (Only `gateway/`; see `migration/baseline/repo-state.md`.)
- [x] Commit the existing Gateway and shell baseline. (Gateway committed;
      shell intentionally left untracked — see `migration/baseline/repo-state.md`.)

**Verify:** open `migration/baseline/repo-state.md` directly — it names the
exact commit each submodule was at, which root files were untracked, and
which of those were deliberately left that way (the shell) versus pulled
in (gateway). If something in your working tree today isn't reflected
there, the baseline is stale and should be re-captured before Plan 03/06
proceed.

## Work packages

### A. Capture repository state

- Record parent, GLC, and ingestion commit IDs.
- Record remotes, branches, submodule pointers, and dirty-file inventories.
- Verify that all required local-only files are either intentionally ignored
  or backed up without capturing credentials.
- Document the selected history import procedure and rollback procedure.

### B. Freeze executable baselines

- Run complete Gateway, ingestion, and GLC suites.
- Run current lint, type, OpenAPI-staleness, and frontend checks.
- Record required Python and Node versions and lockfiles.
- Add one repeatable root-level baseline command or script.

### C. Capture contracts

- Export GLC OpenAPI and Gateway OpenAPI snapshots.
- Capture representative fixtures for:
  - Chat and structured output.
  - Embeddings and profile resolution.
  - Batch chat.
  - SSE streaming and disconnect behavior.
  - Channel WebSockets and webhooks.
  - Transcription and speech.
  - Budget refusal and provider failure.
  - Ingestion run, decision, retry, report, evidence, and cleanup mappings.
- Record environment-variable defaults and precedence.

### D. Inventory callers

- Search code, scripts, services, desktop automation, and documentation for:
  - Port 8111.
  - `GLC_BASE_URL` and other `GLC_*` variables.
  - Imports from `glc.*`.
  - Direct starts of `glc.main`.
  - `/v1/*` routes.
  - `/api/ingestion/*` routes.
- Classify every caller as active, test-only, documentation-only, obsolete,
  or unknown.

### E. Inventory activation state

Added per program-level discussion (see `00-program-roadmap.md`, program
rules): for every domain being moved, record whether it lands
moved-and-active or moved-and-dormant. This is not the same question as "does
it get moved" — everything in scope gets moved — it's "is it mounted/started
by default once it lands." Security, audit, and control (Plan 03) are
always-on by design and are not eligible for dormant status. Channels and
voice (Plan 05) are dormant by default until explicitly activated. Record
this table here so Plans 03 and 05 aren't each re-deciding it ad hoc.

### F. Decide GLC's data-file location

GLC's call ledger and audit log currently default to `~/.glc/gateway.sqlite`
and `~/.glc/audit.sqlite` — not under the root `Database/` folder, unlike
ingestion's SQLite files, which already live under `Database/sqlite/`. This
was not a deliberate migration decision; it's just where GLC has always
written. Decide here, before Plan 03 moves GLC's platform/database code:

- [x] Relocate GLC's ledger and audit databases into `Database/sqlite/`
      alongside ingestion's, so all data is queryable/connectable in one
      place (Aryaman's stated preference — nothing should be "floating in a
      folder and I don't remember it").
- [ ] Keep them at `~/.glc/`, because `glc_v5/glc/db.py`'s docstring gives a
      real reason for that location — daemon-installability without writing
      into the source tree — and that reason may still apply once GLC lives
      inside Gateway.
- [ ] Something else; describe it below.

This decision is binding on Plan 03's "Database layout" decision (§1).

## Explicitly out of scope

- Moving source files.
- Changing imports or ports.
- Refactoring providers or ingestion internals.
- Removing submodules.

## Exit gate

- All three baselines are green and recorded.
- Current work exists in recoverable commits.
- Gateway is tracked.
- History policy is approved.
- Contract snapshots and caller inventory are committed.
- Unknown callers have an owner or an explicit compatibility requirement.
- Every in-scope domain has a recorded activation state (active or dormant).
- GLC's data-file location decision (Work Package F) is made, not assumed.

## Baseline artifacts (2026-09-14)

All Work Package A-F output lives under `migration/baseline/` at the AI OS
root — start at `migration/baseline/README.md`.

## Aryaman's comments

Add corrections to ownership, history, compatibility, or caller assumptions
here before this plan is implemented.
