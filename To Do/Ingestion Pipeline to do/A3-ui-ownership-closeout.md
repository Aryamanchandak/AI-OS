# A3: Gateway Serves Every Screen (Closeout Checklist)

Stage A, item 3. **Mostly done.** This is a checklist, not new work.

## The goal

Ingestion only answers API requests. Gateway is the single front door
that serves every screen you see, for both ingestion and GLC. You agreed
this is housekeeping rather than new capability.

## Already done

- The ingestion review API now lives inside Gateway, at the same web
  addresses as before.
- Ingestion no longer has its own web server or screens.
- One app (the "shell") holds every screen, and Gateway serves it.
- GLC's screens (Channels, LLM, Observability) are in the same app, in
  the same menu as Ingestion.

## What's left

1. **One outdated README line** in the old ingestion repo points at where
   the review screen used to live. Don't edit the old repo; it's being
   retired. Instead, add a short "Ingestion" section to Gateway's README
   saying where the API, screens and code live.
2. **Old duplicate GLC pages** are removed as part of Gateway Plan 07.
   Tick this off when Plan 07 closes.
3. **The old Unified UI plan** has already been marked as replaced.
4. **New screens from Stage A** (the clerk and Judge's desk from A1, the
   whole-highlight review from A1, the settings panel from A4) all go in the shell.
   That's consistent with this rule.

## Done when

- Gateway Plan 07's exit gate is met.
- Nothing in Gateway's code imports the old ingestion repo.
- Gateway's README says where ingestion's API, screens and code live.
- Every menu item in the app is served by Gateway itself, with no links
  out to the old GLC port (8111).

When all four are true, this item counts as done for the Stage B
checklist.

## Where in the code

- API: `gateway/src/gateway/ingestion/server.py`, registered through
  `gateway/src/gateway/app/router_registry.py` →
  `gateway.ingestion.routes.registration()`, at `/api/ingestion/*`.
- Shell served from `gateway/src/gateway/app/main.py` (`SHELL_DIST`). The
  menu is in `shell/src/components/AppShell.tsx`.
- Stale pointer: `ingestion-pipeline/merged-ingestion/README.md` (around
  line 91).
- Import check: `grep -rn "cockpit\|merged-ingestion\|merged_ingestion" gateway/src`
  should return no import hits.
- Plan 07: `To Do/Gateway to do/GLC and ingestion gateway migration/`.
- Superseded plan: `To Do/UNIFIED UI/UNIFIED_UI_PLAN.md`.

## Aryaman's comments

