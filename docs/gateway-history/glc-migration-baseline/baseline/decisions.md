# Plan 01 decisions — recorded 2026-09-14

Decisions confirmed by Aryaman during baseline capture. Binding on later
plans as noted in `01-baseline-and-ownership-decisions.md`.

## §1 History policy

**Preserve full history.** Use a history-aware import (`git subtree`/
`git filter-repo`) for both GLC and ingestion when they're structurally
moved into the gateway later; move paths in separate follow-up commits. See
`repo-state.md`.

## §2 Compatibility policy

**Adopted the proposed default** (not re-asked — conservative, forecloses
nothing): freeze `/v1/*` (GLC) and `/api/ingestion/*` (Gateway) contracts —
URLs, status codes, response bodies, SSE frames, WebSocket behavior — byte
for byte, until caller migration is complete. No exceptions listed. See
`contracts.md`.

## §3 Import landing area

**Adopted the proposed default** (not re-asked): when GLC/ingestion are
later structurally imported, land each first under a temporary
`gateway/_migration/` prefix; no reorganizing in the same commit as the
import. Not yet applicable — Plan 01 explicitly excludes moving source
files.

## §4 Dirty working trees

- GLC's and ingestion's uncommitted work: reviewed (diffed for secrets,
  checked deletions) and committed in their own repos. See `repo-state.md`.
- Untracked root files: **track `gateway/`, `Project plan/`, and `To Do/`.**
  `Database/`, `AI Agent/` (each its own separate git repo / large personal
  data), and `shell/` stay untracked and are now explicitly gitignored.
  `Project plan/`/`To Do/` were initially left ignored too, then revised
  once it was clear this plan's own decision record
  (`01-baseline-and-ownership-decisions.md`) lives inside `To Do/` — see
  `repo-state.md`.
- Gateway and shell baseline: gateway is now committed; shell was left
  untracked per the above (not part of this plan's exit gate).

## Work Package F — GLC's data-file location

**Relocate GLC's ledger and audit databases into `Database/sqlite/`**,
alongside ingestion's, per Aryaman's stated preference (everything
queryable in one place). This decision is **binding on Plan 03's "Database
layout" decision (§1)** — Plan 03 is where `GLC_GATEWAY_DB`/`GLC_AUDIT_DB`
defaults in `glc/db.py` and `glc/audit/store.py` actually get changed; Plan
01 only records the decision (see exit gate: "made, not assumed"), it does
not implement it — implementing it would be changing GLC source, which
Plan 01 explicitly excludes.
