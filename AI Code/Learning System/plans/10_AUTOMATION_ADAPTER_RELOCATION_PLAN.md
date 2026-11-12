# Automation Adapter Relocation — Change Record

**Date:** 2026-07-18
**Status:** Executed. Destination: new sibling repo `Automation Personal/study-automation`
(option 1 in §5, below — a new sibling project mirroring `mcp_server`'s relationship to this
package, once the user confirmed proceeding without further narrowing the choice).
**Precedent:** `09_MCP_ADAPTER_RELOCATION.md`. That document was the template for this move; where
this plan doesn't repeat a detail, the same reasoning applies.
**Scope:** Automation code location only. No change to `core/`, `repositories/`, `storage/`,
`scheduling/`, `types/`, `config/baseline.json`, or `StudyCore`'s method signatures.

## 1. Why this is next

`00_RESOLVED_MVP_AND_ARCHITECTURE.md` §2 anticipated exactly this, for both adapters:

> If deployment later requires physical folders under separate Automation and MCP roots, both
> adapters should import the same versioned core package. Copying the learning logic into both
> folders is rejected because the two copies would drift.

The MCP half of that sentence is done (plan 09: `mcp/` moved into `mcp_server`). This repo is
currently *not yet* a pure library — `automation/generate.py` and its shell launcher are still the
one remaining adapter living inside `study_system` rather than calling into it from outside. Moving
it out completes the "base logic only" shape the user is stripping this repo down to: after this
move, `study_system` contains only `core/`, `repositories/`, `storage/`, `scheduling/`, `types/`,
`config/` — no adapter code of any kind, MCP or automation.

## 2. What would move

| Old location (this repo) | Becomes |
|---|---|
| `src/study_system/automation/generate.py` | Ported into the new host, importing `study_system` as an installed/pathed dependency (same relationship `mcp_server/tools/study/adapter.py` has to this package now) |
| `scripts/run_study_automation.sh` | Moves with it — the shell launcher belongs next to the job it launches |
| `study-automation` console entry point (`pyproject.toml`) | Removed from this repo's `pyproject.toml`; re-added in the new host's own `pyproject.toml` if it uses one, or replaced by a direct script path in the new host's launcher |
| `tests/unit/test_automation_lock.py` | Moves with the code it tests (preflight/locking behavior is automation-adapter behavior, not core behavior) |

**Stays here, unaffected:** `core/study_core.py`, `core/baseline.py`, `core/gateway.py`,
`repositories/`, `storage/mvp_store.py` + migrations, `scheduling/scheduler.py` (+ the
`scheduler.py` compat shim), `types/`, `config/baseline.json`. These are exactly what plan 09 left
untouched for the MCP move, for the same reason: the adapter is what's relocating, not the logic it
calls.

## 3. How the move would be done (mirrors plan 09 §3)

1. Port `generate.py` verbatim into the new host, updating only the import path if `study_system`
   stops being installed in editable/pathed mode there (same "no logic changes" constraint plan 09
   applied to `StudyMCPTools`/`build_mcp_core`).
2. Move `scripts/run_study_automation.sh`, updating only path resolution (central Database-root
   discovery via the `AI Code` ancestor search must still work from the new location — verify this
   explicitly, since the ancestor-walk logic is location-sensitive in a way plain imports aren't).
3. Verify the relocated code runs correctly *before* deleting anything here (same order plan 09
   used: port → verify → delete).
4. Delete `src/study_system/automation/`, `scripts/run_study_automation.sh`,
   `tests/unit/test_automation_lock.py`, and the `study-automation` entry point from this repo's
   `pyproject.toml`. Run `uv lock` afterward if any dependency becomes unused as a result (unlikely
   here — automation doesn't pull in a dependency the way the `mcp` SDK did).
5. Update `CLAUDE.md` and `README.md` in this repo to remove the automation adapter from the
   "what's implemented here" list and point at the new host, the same way plan 09 §3 step 5 did for
   MCP.

## 4. Verification checklist (mirrors plan 09 §4)

- [ ] Relocated `generate.py` still passes preflight, single-run-lock, and idempotent-generation
      behavior against a real temporary Database root (the same manual end-to-end check plan 07 §7
      ran once against the pre-move code).
- [ ] `bash -n` on the relocated shell launcher.
- [ ] Central Database-root ancestor-search still resolves correctly from the new file location —
      this is the one part of the move that isn't a pure copy, since that logic walks up from
      `__file__`'s location looking for an `AI Code` ancestor.
- [ ] After deletion here: full `study_system` test suite still passes (expect 42 minus
      whatever `test_automation_lock.py` contributed — check its count before deleting).
- [ ] `mypy --strict` still clean across remaining `study_system` source files.
- [ ] grep confirms no remaining reference to `study_system.automation`, `study_system/automation`,
      `study-automation`, or `run_study_automation` in `src/`, `tests/`, `scripts/`, `README.md`, or
      `CLAUDE.md` (plans/07, plans/09, and this plan may still mention the old location as dated
      historical record — that's expected, same exception plan 09 §4 noted).

## 5. Destination decision (resolved)

Three options were surfaced (a new sibling repo; promoting `Automation Personal/` itself; folding
into some other generic "scheduled jobs" host). The user deferred narrowing it further and said to
proceed; `Automation Personal/study-automation` — a new sibling repo next to `study-system`,
`unified-ingestion`, and `podcast-pipeline` in the same directory — was chosen as the closest match
to option 1/2 (a dedicated project, placed consistently with how this directory already hosts one
single-purpose automation project per concern), sibling to `study-system` rather than living at the
top-level `AI Code/` root the way the multi-project `mcp_server` does (automation is
study-specific only, unlike `mcp_server`'s shared multi-group role).

## 6. What was actually moved

| Old location (this repo) | New location (`study-automation`) |
|---|---|
| `src/study_system/automation/generate.py` | `generate.py` (repo root) — logic byte-identical; only addition is a `_find_workspace_root()`/sys.path bootstrap at the top, before the `study_system.*` imports, mirroring `mcp_server/mcp_server.py`'s existing convention for the same package |
| `scripts/run_study_automation.sh` | `scripts/run_study_automation.sh` — same structure; `.venv` activation and dependency check now point at the sibling `study-system/.venv` (this project declares no dependencies of its own), and the two `study_system.automation.generate` module invocations became direct `generate.py` path invocations |
| `study-automation` entry point (`pyproject.toml`) | Removed here; not recreated as a console script in the new host — `generate.py` is invoked by path, same as the shell launcher already did internally |
| `tests/unit/test_automation_lock.py` | `tests/test_automation_lock.py` — unchanged except the import (`from study_system.automation.generate import ...` → `from generate import ...`) |

**Stayed here, unaffected:** `core/study_core.py`, `core/baseline.py`, `core/gateway.py`,
`repositories/`, `storage/mvp_store.py` + migrations, `scheduling/scheduler.py` (+ the
`scheduler.py` compat shim), `types/`, `config/baseline.json`.

The new host's `pyproject.toml` declares no dependencies of its own — it reuses study-system's
`.venv`, since it has nothing to depend on beyond the `study_system` package it imports.

## 7. Verification performed

1. **New-host test run**, before touching this repo: `study-system/.venv/bin/python -m pytest -q`
   from `study-automation/` → `3 passed`.
2. **Manual end-to-end run** against a real temporary Database root, direct script invocation:
   `generate.py --check` → `status: ok`; first `generate.py` run → `cards_inserted: 1`; second run
   (same baseline, unchanged concept) → `cards_inserted: 0` — confirms idempotency survived the
   move.
3. **Shell launcher end-to-end run** (`scripts/run_study_automation.sh --baseline ... --count 1`)
   against a temp `STUDY_SYSTEM_DATABASE_ROOT` → preflight, generation, and a real log file under
   `<root>/Logs/study_system/` all worked correctly from the new location.
4. **Finding: the ancestor-search location-sensitivity concern in the original plan (§3 step 2) was
   unfounded.** `BASELINE_PATH` and `default_database_root()` are anchored to
   `config/baseline.json`'s own path inside *this* repo
   (`Path(__file__).resolve().parents[3]` in `core/baseline.py`, and `load_baseline` passing
   `path.parent` into `default_database_root`) — not to the calling adapter's file location at all.
   Moving `generate.py` to a different repo required no changes to that resolution logic; the
   shell script's own independent copy of the same ancestor-walk (for the log directory) was the
   only genuinely location-sensitive piece, and it was verified directly in step 3.
5. After deleting the study-system side:
   ```text
   uv lock                                          → Resolved 35 packages, no errors
   .venv/bin/python -m pytest -q                    → 39 passed (down from 42; the 3 deleted
                                                        automation-lock tests account for the difference)
   .venv/bin/python -m mypy src/study_system        → Success: no issues found in 17 source files
   bash -n scripts/run_study_automation.sh (new host) → passed
   git diff --check                                 → passed
   ```
   grep confirmed no remaining reference to `study_system.automation`, `study_system/automation`,
   `study-automation` (as an in-repo path), or `run_study_automation` in `src/`, `tests/`,
   `pyproject.toml`, `README.md`, or `CLAUDE.md` here — remaining hits are all intentional pointers
   to the new sibling project.

A stray build artifact (`src/study_system.egg-info/`, already `.gitignore`d, referencing the old
`study-automation` entry point) and stale `__pycache__` directories (including an empty leftover
`src/study_system/mcp/__pycache__/` from the earlier MCP move) were also cleaned up while verifying
— neither was tracked by git.

## 8. Not done in this pass

- No behavior change to automation logic — pure code-location move, same constraint plan 09 §5
  held for MCP.
- No change to `StudyCore` method signatures.
- No console-script entry point was recreated in the new host; `generate.py` is run by direct path
  (same as the shell launcher's internal invocation), which was simpler than adding packaging for a
  single-script project.
- Does not resolve any of plan 07 §6's still-open production-acceptance gates (KG/vector adapters,
  live gateway acceptance, migration) — those are independent of where the adapter code physically
  lives.
