# Baseline Capture

**Purpose:** Satisfy plan `01_PRESERVATION_AND_MIGRATION.md` §3 ("Baseline capture before editing") before continuing the migration/automation work in `02_STUDY_AUTOMATION_MCP_AND_CONFIG.md`.

**Captured:** 2026-07-16, immediately after `git init` on this repository (first commit `54ba836`).

## 1. Current commands and expected outcomes

Legacy CLI (`src/study_system/cli/app.py`, entry point `study`):

| Command | Outcome |
|---|---|
| `study ingest [--vault-subset X] [--dry-run] [--with-quiz]` | Scans vault, extracts concepts/triplets/facts, generates flashcards (+ quiz MCQs if flagged), runs quality sampling |
| `study review [--max-cards N]` | Interactive terminal FSRS flashcard session |
| `study quiz [-n N] [--concept-ids ...]` | Interactive terminal MCQ quiz session |
| `study kg-review [--limit N]` | Interactive approve/reject loop over pending KG edges |
| `study chat` | Phase 3 intent-routed chat loop |
| `study calibration` | Confidence calibration report |
| `study overrides [--consolidate]` | Show/consolidate user override log |
| `study spend` | Print LLM spend log |
| `study revert-fsrs` | Roll back FSRS weights to a prior persisted version |
| `study status` | Print current pipeline/config status |

New MVP layer (not yet exposed as a CLI; called as library code):

| Entry point | Outcome |
|---|---|
| `python -m study_system.automation.generate [--baseline PATH] [--count N]` (also installed as `study-automation`) | Headless: loads baseline+overrides, selects unseen concepts from a JSON KG export, generates cards via `TemplateCardGenerator`, persists to `MVPStore`, prints a JSON run summary |
| `scripts/run_study_automation.sh` | Fail-fast launcher wrapping the above; activates `.venv`, sets `PYTHONPATH`, tees logs |
| `study_system.mcp.tools.StudyMCPTools` | Plain Python wrapper over `StudyCore`, not yet bound to an actual MCP protocol server |

### Which commands are actually used vs merely present

No `.env` file and no runtime `data/` directory exist anywhere in this repo (confirmed by filesystem search). This means **none of the legacy CLI commands have been run against real data in this checkout** — `study ingest` has never completed, there is no vault configured, and no SQLite file has ever been created here. Every legacy command above is present and importable but unverified against real usage. Treat all of them as "specified, not confirmed used" until proven otherwise.

The new MVP layer (`automation/generate.py`, `mcp/tools.py`) is exercised only by the unit tests in `tests/unit/test_mvp_core.py` and `tests/unit/test_mvp_store.py` — also never run against real data.

## 2. Real data / backup status

- No SQLite database file exists anywhere under this repo or under the workspace's central `Database/` root (`sqlite`, `*.db` search came up empty for study-system).
- No `STUDY_ROOT` concept directory tree exists on disk.
- No vault path is configured (`VAULT_ROOT` has no `.env` to source from).

**Conclusion: there is no real learning data to lose.** Plan 01 §6's data-migration safeguards (never test against the only copy, backup first, forward-only migrations) become live concerns only once a real `study_system.db` exists. Until then, "migration" is theoretical — the actual remaining risk is losing *code/prompt/design* work, not rows.

If/when a real vault + `.env` are configured and `study ingest` is run for the first time, re-run this capture step and add:
- SQLite file path, size, `sqlite3 .tables` output, row counts per table.
- A `sqlite3 .dump` (or file copy) backup taken before any further schema/code changes.
- `STUDY_ROOT` concept directory listing.

## 3. Schema / migration versions on record

`src/study_system/storage/migrations/`:

| File | Introduces |
|---|---|
| `001_initial.sql` | `vault_manifest`, `extractions`, `concepts`, `cards`, `reviews`, `spend_log`, `schema_migrations` |
| `002_kg_quality_quiz.sql` | `kg_edges`, `grounding_checks`, `rubric_scores`, `quiz_sessions`, `quiz_attempts`, `quiz_feedback` |
| `003_phase3.sql` | `app_config`, `chat_history`, `concept_mastery`, `fsrs_weights_history`, `overrides_cache` |
| `010_mvp_four_table_schema.sql` | New, separate MVP schema: `cards`, `review_state`, `generation_runs`, `overrides` (used by `storage/mvp_store.py::MVPStore`, **not** `storage/sqlite_store.py::SqliteStore`) |

Two schemas currently coexist in the codebase:
1. **Legacy schema** (migrations 001-003) — owned by `storage/sqlite_store.py`, used by the legacy CLI (`ingest`, `review`, `quiz`, `chat`, etc).
2. **MVP schema** (migration 010) — owned by `storage/mvp_store.py`, used by the new `core/study_core.py` + `automation/` + `mcp/` layer. Deliberately minimal ("exactly four study-owned tables" per `tests/unit/test_mvp_store.py`).

Per plan 01 Step A ("Wrap") / Step D ("Migrate storage"), these are expected to converge later — the MVP schema is the target, the legacy schema is what real migration would read from once real data exists. Since no real data exists yet (§2), there is nothing to migrate today; this is a forward design decision, not a live migration debt.

## 4. Configured data paths (as of this capture)

From `core/config.py` (legacy `Config`, env-driven):
- `VAULT_ROOT` → default `./vault`
- `STUDY_ROOT` → default `./data/concepts`
- `SQLITE_PATH` → default `./data/study_system.db`
- `CHROMA_PATH` → default `./data/chroma`

From `core/baseline.py` (new MVP `StudyBaseline`, `config/baseline.json`):
- `database_root` → `null` in the checked-in file, resolved at runtime by `default_database_root()`: `STUDY_SYSTEM_DATABASE_ROOT` env override, else the nearest ancestor directory literally named `AI Code` plus `/Database`, else `<cwd>/Database`. On this machine that resolves to `/Users/aryamanchandak/Documents/AI Code/Database`.
- `sqlite_relative_path` → `Ingested/SQLite/study_system/study_system.db` (does not exist yet under `Database/`)
- `kg_concepts_path` / `vector_snippets_path` → `null`; `automation/generate.py::build_core()` raises `RuntimeError` if `kg_concepts_path` is unset, so automation cannot run at all yet without a JSON KG export or a production adapter.

## 5. Test baseline

`uv sync --extra dev && uv run pytest -q` → **32 passed**, 0 failed, 0 skipped (captured 2026-07-16, first run in this checkout; `uv` had to create `.venv` and install dependencies from scratch, confirming this had not been run here before).

Covered by existing tests: FSRS scheduler transitions, vault manifest hashing, MVP store schema/overrides, `StudyCore` unseen-concept selection + card generation + rating + stateless Feynman/challenger heuristics. Gaps against plan 01 §4's checklist are tracked as a follow-up task (see `plans/01_PRESERVATION_AND_MIGRATION.md` §4 and the session's task list).
