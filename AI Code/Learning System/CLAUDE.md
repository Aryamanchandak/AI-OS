# Study System — Coding Guide & Architecture Reference

**Last updated:** 2026-07-18
**Stack:** Python 3.11+ · SQLite · FSRS-4.5 · shared LLM gateway (HTTP)
**Domain:** CFA Level 1 exam prep — generates flashcards/quizzes and runs Feynman/challenger
practice from a **final, already-built** knowledge graph and vector store. This repo does not
ingest raw notes; a separate `unified-ingestion` project owns that.

> **Plans live in `plans/`.** `plans/00_RESOLVED_MVP_AND_ARCHITECTURE.md` is the source of truth
> for architecture decisions. `plans/07_MVP_IMPLEMENTATION_VERIFICATION.md` is the current,
> most-authoritative record of what's actually implemented, tested, and still pending. Read both
> before adding a module. This file describes what's built and how it fits together.

---

## What changed

**2026-07-17:** this file previously described an earlier architecture: `ingester.py`,
`extractor.py`, `generator.py`, `chat.py`, `director.py`, a terminal `study` CLI, and a per-file
concept-directory/ChromaDB/NetworkX stack owned by this repo. **All of that was deleted.** It was
superseded by the MVP architecture below, which was built additively alongside it and then, once
verified, had the legacy code removed.

**2026-07-18:** this repo's `mcp/` package (`tools.py`, `server.py`) was moved out entirely, into
the separate `mcp_server` project's `study` tool group. This repo no longer has any MCP code, the
`mcp` SDK dependency, the `study-mcp` entry point, or `scripts/run_study_mcp.sh` — it is a pure
library now, consumed by `mcp_server`. See `plans/09_MCP_ADAPTER_RELOCATION.md`.

**2026-07-18 (later the same day):** this repo's `automation/` package (`generate.py`) and
`scripts/run_study_automation.sh` were moved out the same way, into a new sibling project,
`study-automation`. This repo no longer has an automation job, a shell launcher, a `study-automation`
entry point, or `scripts/` at all — it has no adapter code of any kind now, MCP or automation. See
`plans/10_AUTOMATION_ADAPTER_RELOCATION_PLAN.md`.

If you see references to `study_system.mcp`, `study_system.automation`, `ingester.py`, `chat.py`,
etc. anywhere (comments, old docs, memory), they are stale — check `git log` and
`plans/07`/`plans/09`/`plans/10` before trusting them.

---

## Core Principle

Study-system is **learning logic and orchestration only** — not a frontend, not a data store, not
an ingestion pipeline, and (as of 2026-07-18) not an MCP server or an automation runner either. It
reads a final, read-only knowledge graph and vector store (owned by other projects), and it owns
exactly four SQLite tables for its own learning state. It is consumed two ways, by two sibling
projects that both import it as a library: the `study-automation` project's headless generation
job, and the `study` MCP tool group in the separate `mcp_server` project, which is the only
interface a unified chat client actually talks to. There is one implementation of learning rules
(`StudyCore`) — both callers are thin adapters over it, never duplicate logic. This repo itself has
no adapter code and cannot run anything unattended on its own.

---

## Project Layout

```
study_system/
├── pyproject.toml
├── config/
│   └── baseline.json         ← versioned baseline config (git-tracked); agent has no write path to it
├── src/study_system/
│   ├── core/
│   │   ├── study_core.py     ← StudyCore: the one implementation of all learning rules
│   │   ├── baseline.py       ← StudyBaseline dataclass, effective-config merge (baseline + overrides)
│   │   ├── gateway.py        ← HTTP client for the shared LLM gateway (generation/quality/practice)
│   │   └── prompts/          ← card_generation_flashcard_v1.md, rubric_v1.md, source_grounding_v1.md
│   ├── repositories/
│   │   ├── interfaces.py     ← FinalKGRepository / VectorRepository Protocols (read-only contracts)
│   │   └── json_repositories.py ← file-backed dev/test adapters implementing those protocols
│   ├── storage/
│   │   ├── mvp_store.py      ← the only writer of study-owned SQLite state
│   │   └── migrations/010_mvp_four_table_schema.sql
│   ├── scheduling/
│   │   └── scheduler.py      ← FSRS-4.5 scheduling (stdlib only) — preserved from the earlier system
│   ├── review/
│   │   └── prompts/          ← feynman_evaluator_v1.md, challenger_v1.md (rendered by StudyCore, not a standalone module)
│   └── types/
│       ├── mvp.py            ← ConceptSummary, RetrievedContext, GeneratedCard, and other MVP dataclasses
│       └── card.py           ← Card / FSRS-state types used by scheduling and storage
└── tests/
```

No `automation/`, no `scripts/` — this repo has no runnable entry point of its own anymore.

**Deleted (do not recreate without re-reading `plans/00` and `plans/05`):** `cli/`, `session/`
(chat, director, calibration, overrides), `extraction/`, `generation/`, `ingestion/`, `kg/`,
`vector/`, `validation/`, the old `storage/sqlite_store.py` + migrations 001–003, and their test
fixtures. Their responsibilities now live in other projects or were intentionally cut from MVP
scope (see below).

**Moved (not deleted — now lives in `mcp_server`), do not recreate here:** `mcp/` (`tools.py` →
`mcp_server/tools/study/adapter.py`, `server.py`'s tool definitions → `mcp_server/tools/study/logic.py`),
the `mcp` SDK dependency, the `study-mcp` entry point, `scripts/run_study_mcp.sh`. See
`plans/09_MCP_ADAPTER_RELOCATION.md`.

**Moved (not deleted — now lives in the sibling `study-automation` project), do not recreate here:**
`automation/generate.py` (→ `study-automation/generate.py`, same logic, imports `study_system` as a
sibling package the same way `mcp_server` does), `scripts/run_study_automation.sh` (→
`study-automation/scripts/run_study_automation.sh`), the `study-automation` console entry point. See
`plans/10_AUTOMATION_ADAPTER_RELOCATION_PLAN.md`.

---

## Where responsibilities moved

| Old responsibility | Now lives in |
|---|---|
| Vault ingestion, extraction, semantic hashing | `unified-ingestion` project (separate repo) |
| Knowledge graph identity, aliases, storage | `Database/knowledge-graph` project (separate repo) |
| Vector embeddings/storage | owned by the same final vector store this repo reads from |
| Chat intent routing, terminal `study chat` | the external unified chat client, via `mcp_server`'s `study` tool group |
| MCP adapter/facade + server (`StudyMCPTools`, `build_mcp_core`, tool registration) | `mcp_server/tools/study/adapter.py` + `logic.py` (separate repo) — this repo has no MCP code |
| Headless automation job + shell launcher | `study-automation/generate.py` + `study-automation/scripts/run_study_automation.sh` (separate sibling repo) — this repo has no automation code |
| Session planning / mastery director | not in MVP scope; `SessionPlanner` is preserved only as design reference (plan 00 §10), not implemented here |
| Confidence calibration report | not in MVP scope (deferred, plan 05 §8) |
| Card/quiz generation, quality checks, Feynman/challenger grading | `core/gateway.py` — one HTTP client to the shared LLM gateway, called by `StudyCore` |

---

## Logical Architecture

```text
                Unified chat interface (external repo)
                             |
                mcp_server's `study` tool group (separate repo)
                mcp_server/tools/study/{adapter.py,logic.py}
                             |
                              MCP tools (stateless, 10 tools)
                                     |
                              +------v------+
Scheduled shell runner ----->|  StudyCore  |
(study-automation/generate.py,|  (core/)    |
 separate sibling repo)        +------+------+
                                     |
                  +------------------+------------------+
                  |                  |                  |
             final KG (read)   vector search (read)   study SQLite (owned writes)
             repositories/     repositories/            storage/mvp_store.py
             interfaces.py     interfaces.py
```

Both adapters — `study-automation/generate.py` in the separate sibling `study-automation` repo, and
`mcp_server/tools/study/adapter.py` (`StudyMCPTools`/`build_mcp_core`) in the separate `mcp_server`
repo — construct a `StudyCore` and call its methods. Neither reimplements selection, generation,
scheduling, or persistence logic. This repo exports only `core/`, `repositories/`, `storage/`,
`scheduling/`, `types/`; it has no adapter-layer code of its own anymore.

---

## SQLite Schema — exactly four tables

This is a hard architectural constraint (`plans/00` §3, reaffirmed after a mid-build correction in
`plans/07` §14). Do not add a fifth table without going back through plan 00.

| Table | Owner writes | Purpose |
|---|---|---|
| `cards` | generation (`StudyCore.generate_unseen_cards`) | Card content, concept_id, source/version provenance |
| `review_state` | scheduling (`StudyCore.submit_card_rating`) | FSRS state per card — ease, stability, lapses, due date |
| `generation_runs` | automation job (in `study-automation`) + completed Feynman/challenger evidence | One row per generation run **or** per completed practice evaluation — this is the only audit trail; there is no separate session/practice-attempt table |
| `overrides` | `set_temporary_override` / `cancel_temporary_override` | Time-bounded baseline overrides — allowlisted, bounded, attributed, expiring |

**Feynman/challenger are stateless.** `start_feynman`/`start_challenger` are deterministic,
read-only calls returning a concept/attempt handle. The chat client owns `conversation_so_far` and
passes it back on every evaluation call. Only the *completed* evaluation is persisted, as a
`generation_runs`-style audit row — never mid-interaction state.

---

## The MCP surface — exactly ten tools

**Not implemented in this repo.** Registered in `mcp_server/tools/study/logic.py` (plus two
gateway-fallback tools, `study_record_feynman_evaluation`/`study_record_challenger_evaluation` —
twelve functions total, ten of which are the plan-02 contract), backed by
`mcp_server/tools/study/adapter.py`'s `StudyMCPTools` → this repo's `StudyCore`:

1. `study_generate_cards` — generate cards now, optional temporary count
2. `study_get_due_cards` — fetch due cards for review
3. `study_submit_review` — submit an FSRS rating (1–4), idempotency-key aware
4. `study_start_feynman` — deterministic, read-only start
5. `study_evaluate_feynman` — grades one turn against `conversation_so_far`
6. `study_start_challenger` — deterministic, read-only start
7. `study_grade_challenger` — grades one turn against `conversation_so_far`
8. `study_progress` — cards, final-KG coverage, unseen concepts, due reviews, recent activity, active overrides
9. `study_set_temporary_override` — validated, bounded, expiring override write
10. `study_cancel_temporary_override`

All write tools accept an idempotency key (auto-generated if omitted); retrying with the same key
must not duplicate effects — this is unit-tested, not just documented.

**History:** this repo used to also have its own standalone `mcp/server.py` (a second exposure of
the same tools, for local/direct MCP-client testing). On 2026-07-18 that adapter code was moved
into `mcp_server` outright (not just reconciled) — see `plans/09_MCP_ADAPTER_RELOCATION.md`. There
is now exactly one MCP surface. If this repo's `StudyCore`/`core/study_core.py` method signatures
change, `mcp_server/tools/study/adapter.py` must be updated in the same pass or the two will drift.

---

## Configuration

`config/baseline.json` is the versioned baseline (git-tracked, reviewed like code): generation/
review limits, models, prompt versions, central SQLite location, final KG/vector source paths,
LLM gateway URL, quality thresholds, FSRS weights. Loaded into `StudyBaseline`
(`core/baseline.py`).

**The agent has no write path to this file.** Temporary changes go through
`study_set_temporary_override`, which validates against `override_max_values`, timestamps, and
attributes the change, and writes to the `overrides` SQLite table — never to the baseline file.
Effective config at request time = baseline merged with active (non-expired) overrides
(`core/baseline.py::effective_config`).

`kg_concepts_path` / `vector_snippets_path` are intentionally `null` in the checked-in baseline —
the automation runner (in `study-automation`) fails fast until these are pointed at real
final-KG/vector exports (or a production `FinalKGRepository`/`VectorRepository` adapter replaces
the JSON dev adapters in `repositories/json_repositories.py`).

---

## Data Location

Study-system's repository stores **no runtime data**. Everything — SQLite DB, logs, the single-run
lock file — lives under a central `Database/` root resolved by walking up to find an `AI Code`
ancestor directory (see `core/baseline.py`; the automation job's copy of this same ancestor-search
logic now lives in `study-automation/generate.py`), never inside this checkout. `.gitignore`
already excludes `logs/`, `data/`, `*.db`.

Note: `BASELINE_PATH` and the database-root resolution are anchored to `config/baseline.json`'s own
location inside *this* repo (`Path(__file__).resolve().parents[3]` in `core/baseline.py`), not to
wherever the calling adapter's code happens to live. That's why moving `automation/generate.py` out
to a separate repo didn't require changing any path-resolution logic — the adapter just imports
`study_system` and gets the same baseline/database paths regardless of where the adapter file sits.

---

## Data & Control Flow

### Automation (`study-automation/scripts/run_study_automation.sh` → `study-automation/generate.py`, separate sibling repo)

```
1. resolve central Database root; acquire single-run flock (non-blocking — fails fast if held)
2. load StudyBaseline from config/baseline.json, merge active overrides
3. preflight: validate KG/vector paths configured, gateway reachable
4. StudyCore.select_unseen_concepts() — final KG concepts with zero existing cards (binary gate,
   not a fluency/coverage score — plan 00 §7 deliberately rejects a second competing measure)
5. StudyCore.retrieve_context() per concept — re-queried each run, no durable context cache
6. StudyCore.generate_unseen_cards() — gateway-backed generation + quality check, idempotent on
   (concept_id, source_version_hash)
7. mvp_store writes: cards + one generation_runs audit row
8. exit non-zero on any failure
```

### MCP (stateless, one call per tool invocation — implemented in `mcp_server`, not here)

Each tool call (in `mcp_server/tools/study/`) constructs/reuses a `StudyCore` from this package,
does exactly one thing (generate, fetch due, submit rating, one Feynman/challenger turn, read
progress, set/cancel an override), and returns. No tool holds conversation or session state between
calls — the chat client does.

---

## Known Open Items (see `plans/07` for full detail)

1. ~~Two MCP exposures need reconciling~~ — resolved 2026-07-18 by moving the MCP adapter/server
   into `mcp_server` outright, eliminating the standalone copy. See `plans/09`.
1a. ~~Automation adapter still lived inside this repo~~ — resolved 2026-07-18 by moving
   `automation/generate.py` and its shell launcher into the new sibling `study-automation` repo,
   the same treatment plan 09 gave MCP. This repo is now a pure library with no adapter code of any
   kind. See `plans/10_AUTOMATION_ADAPTER_RELOCATION_PLAN.md`.
2. **Production KG/vector adapters not wired** — `repositories/json_repositories.py` are dev/test
   fixtures; a production adapter must implement `FinalKGRepository`/`VectorRepository` against the
   real knowledge-graph and vector projects.
3. **Live LLM gateway acceptance pending** — `core/gateway.py` is unit-verified against a fake, not
   yet run end-to-end against a live gateway.
4. **No existing production data to migrate** — confirmed in `plans/BASELINE_CAPTURE.md`: no real
   vault/SQLite data exists in any checkout, so plan 01's migration safeguards are currently dormant.
5. **UI is intentionally external** — no dashboard, TUI, or standalone frontend belongs in this
   repo per `plans/00` §6 and `plans/05` §4/§10. If a local TUI is ever built here, it needs its own
   promotion record per `plans/05` §1, not ad hoc addition.

---

## Testing

```bash
uv run --no-dev --with pytest python -m pytest -q       # 39 passed as of 2026-07-18 (post MCP + automation move)
uv run --no-dev --with mypy python -m mypy src/study_system   # strict, clean across all source files
```

Coverage includes: exact four-table schema assertion, deterministic unseen-concept selection,
generation/review/override idempotency, due-card filtering and FSRS transitions, Feynman/challenger
statelessness and evidence persistence, and override validation/expiry. **Automation preflight and
single-run locking is no longer tested here** — that coverage moved with the adapter code to
`study-automation/tests/test_automation_lock.py` (see `plans/10_AUTOMATION_ADAPTER_RELOCATION_PLAN.md`).
**The exact ten-tool MCP surface is also no longer tested here** — that coverage belongs with the
adapter code in `mcp_server` (verified there by import/signature/smoke-call, since that project has
no pytest suite; see `plans/09_MCP_ADAPTER_RELOCATION.md`).
