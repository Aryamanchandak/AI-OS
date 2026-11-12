# Database/ — Revision Suggestions

**Author:** review pass, 2026-07-05
**Scope reviewed:** everything under `Database/` except `.venv/`, `__pycache__/`, `.mypy_cache/`, and third-party site-packages.

> **Status: IMPLEMENTED 2026-07-05.** Tiers A (docs), B (code, except the optional B4 print→logging
> cleanup), and C (hygiene) below have been applied. Not done, by design: **C4** (whether to make
> `Database/` a git repo — a decision left to you), **B4** (optional/cosmetic), and all of
> **Tier D** (net-new work: tests, the sqlite consumer). This file is retained as the record of
> what was changed and why.

---

## TL;DR

**The running code is in good shape.** The `Raw Data/lib` core + `knowledge_graph` +
`vector_db` consumers are coherent, defensive, and idempotent, and the ledger confirms the
pipeline has actually run end-to-end (`kg,extracted,done`; `kg,written,done`; `vector,upserted,done ×3`).

**The problem is documentation drift, plus repo hygiene.** A large fraction of the Markdown
in this tree still describes a `study_system` / FSRS / quiz / CFA app that **does not exist
anywhere under `Database/`**. Multiple docs were only half-migrated (a fresh "current truth"
header bolted on top of a stale study_system body). Two per-package `WORKFLOW.md` files
describe APIs that no longer exist or omit the real pipeline entry point entirely. Several
build/venv/cache artifacts are sitting in the tree.

Work is tiered by **risk**, so you know what's safe to do blindly vs. what needs judgment:

- **Tier A — Documentation reconciliation** (highest value, low code risk). Fix the drift.
- **Tier B — Code behavior** (small, optional, verify each before changing).
- **Tier C — Repo hygiene** (delete artifacts, add `.gitignore`).
- **Tier D — Known gaps** (informational — no tests, sqlite consumer unbuilt).

**Do NOT delete `Database/sqlite/podcast_pipeline.db` or the `Database/sqlite/` folder** —
per `sqlite/TODO.md` and the top-level `WORKFLOW.md`, that is intentional future-scope
(its producer lives elsewhere). See Tier C for what *is* safe to remove.

---

## Ground truth (what actually exists, so every edit can be checked against it)

A personal **data-capture pipeline** ("Raw Data storage rework"):

1. `Raw Data/lib/` — shared core: `capture.py` (write immutable bronze `.md` + register in
   ledger), `ledger.py` (`items`/`processing`/`runs` in `sqlite/ledger.db`), `ids.py`,
   `paths.py`, `bronze.py`, `config.py` (`SOURCE_REGISTRY`, `ROUTING`, `TERMINAL_STAGE`),
   `heartbeat.py` (run bookkeeping + staleness osascript nag).
2. `knowledge-graph/` — KG consumer: `run.py` → `pending("kg","written")` loop →
   `extraction.py` (Claude triplets → JSONL, idempotent) → `ingestion.py::write_kg`
   (UNWIND MERGE into Neo4j) → `kg_store.py` (`KGStore`).
3. `vector-db/` — vector consumer: `run.py` → `pending("vector","upserted")` loop →
   `write.py::write_vector` → `ingestion.py::chunk_text` → `vector_store.py::VectorStore`
   (ChromaDB + local Ollama `nomic-embed-text`).
4. `sqlite/` — `ledger.db` (live) + `podcast_pipeline.db` (future-scope, producer elsewhere).

There is **no** `study_system` package, **no** FSRS scheduler, **no** quiz/review loop, **no**
`cli/app.py`, and **no** top-level `src/` in this tree. Any doc that says otherwise is stale.
The single source-of-truth trace is the **top-level `Database/WORKFLOW.md`** (accurate — keep it).

---

## Tier A — Documentation reconciliation

### A1. Doc-by-doc disposition

| File | Disposition | Reason |
|---|---|---|
| `WORKFLOW.md` (top level) | **KEEP — authoritative** | Accurate end-to-end trace of the real pipeline. Use as the reference for reconciling everything else. |
| `IMPLEMENTATION_PLAN.md` | **KEEP — authoritative** | Has an explicit "Reconciliation with shipped code" note; shipped names are marked authoritative. Its aspirational bodies (`storage_core`, `STORAGE_ROOT`) are fine because the reconciliation table overrides them. |
| `vector-db/VECTOR_ALIGNMENT_PLAN.md` | **KEEP — authoritative** | Marked ✅ IMPLEMENTED 2026-07-05; matches the code. |
| `sqlite/TODO.md` | **KEEP — accurate** | Correctly separates `ledger.db` (live) from `podcast_pipeline.db` (future). |
| `Raw Data/Agent Memory/README.md` | **KEEP** | Unrelated agent-memory docs; out of pipeline scope, not stale. |
| `knowledge-graph/CLAUDE.md` | **REWRITE** | Entirely describes the `study_system` monorepo (FSRS, quiz, CLI, top-level `src/`, 3-package install order). None of it applies to this tree. |
| `knowledge-graph/AGENTS.md` | **REWRITE** (or delete) | Same stale study_system router as CLAUDE.md, Codex-facing copy. |
| `vector-db/CLAUDE.md` | **TRIM** | Has a correct "Current truth (2026-07-05)" header, then retains the full stale study_system router below it. Keep the header, delete everything from "Workspace — Coding Guide (older, study_system-era router)" down. |
| `vector-db/AGENTS.md` | **REWRITE** (or delete) | Stale study_system router, no "current truth" header at all. |
| `knowledge-graph/WORKFLOW.md` | **DELETE or REWRITE** | Documents a `KGIngester.ingest/ingest_batch/ingest_triplets` API that no longer exists in `ingestion.py` (now just `write_kg`), with line numbers that don't match, and claims extraction "never raises" (the pipeline path raises with `strict=True`). Superseded by the top-level `WORKFLOW.md`. |
| `vector-db/WORKFLOW.md` | **DELETE or REWRITE** | Documents only the generic `VectorIngester` library path; never mentions `run_vector`, `write_vector`, the ledger, or bronze — i.e. it omits the actual pipeline entry point. Line numbers are stale. Misleading as-is. |
| `knowledge-graph/KG_NEW.md` | **KEEP but annotate** | Historical build plan for the KG slice; accurate to intent but references out-of-tree `STORAGE_PRINCIPLES.md`. Add a one-line "historical — implemented, see top-level WORKFLOW.md" banner, or move to a `docs/history/` folder. |
| `knowledge-graph/where we are.md` | **DELETE** | Raw agent-transcript scratch dump ("✻ Cogitated for 2m 18s"). Describes a `KGIngester`/`ingest_triplets` API that isn't the shipped one. No lasting value. |
| `knowledge-graph/src/knowledge_graph/kg_store.md` | **UPDATE** | "Last updated 2026-06-25"; check it against current `kg_store.py` (it predates pipeline alignment). Verify method list/line refs; correct or delete. |
| `vector-db/src/vector_db/vector_store.md` | **UPDATE** | Same vintage (2026-06-25); verify against current `vector_store.py` (esp. `ensure_embedder`/`assert_writable`, which are newer than this doc). |

### A2. Make the `STORAGE_PRINCIPLES.md` references resolvable (do NOT copy the file)

`grep -rl "STORAGE_PRINCIPLES\|Constitution/"` hits `IMPLEMENTATION_PLAN.md`,
`knowledge-graph/KG_NEW.md`, `vector-db/CLAUDE.md`, `vector-db/VECTOR_ALIGNMENT_PLAN.md`.

These references are **correct and should stay** — `STORAGE_PRINCIPLES.md` is the canonical,
authoritative principles doc (it's what the `P1`/`P4`/`P6`/`P7`/`P11` markers throughout the
code and docs refer to). It intentionally lives one level up in a shared `Constitution/` folder
so it isn't duplicated per-project. **Do not copy it into `Database/`** — a single source of
truth is the whole point.

The only problem is that a bare `Constitution/STORAGE_PRINCIPLES.md` reference isn't resolvable
from inside `Database/`. Fix: make each reference point at a path a reader can actually follow.
The file is at:

```
/Users/aryamanchandak/Documents/AI Code/Constitution/STORAGE_PRINCIPLES.md
```

i.e. `../Constitution/STORAGE_PRINCIPLES.md` relative to the `Database/` root. Update each of
the four references to use that relative path (preferred, so it survives the tree moving) or
the absolute path, so nobody is sent chasing a file that looks missing.

### A3. After rewriting, verify nothing still lies

`grep -rin "study_system\|study-system\|FSRS\|quiz\|CFA\|Feynman" --include="*.md" .`
(excluding `.venv`) should return **only** intentional historical mentions
(e.g. IMPLEMENTATION_PLAN's reconciliation table, the vector `pyproject.toml` description
string). Nothing should present study_system as *current*.

---

## Tier B — Code behavior (small; verify each before changing)

These are minor. The code works. Treat each as "confirm, then decide."

### B1. `run_vector` never closes the store / never fails fast
`vector-db/src/vector_db/run.py:38` — `run_kg` calls `store.close()`; `run_vector` does not,
and it never calls the `assert_writable(collection)` that `vector_store.py` provides
specifically for "fail the whole run fast when Ollama is installed-but-down." As written, an
Ollama-down run marks every item `(vector, upserted, failed)` one-by-one instead of aborting
early. **Suggested:** call `store.assert_writable(COLLECTION)` once before the loop; add a
`store.close()`/`finally` if `VectorStore` grows a close method. Low priority — behavior is
correct, just noisier than intended.

### B2. Model ID `claude-sonnet-4-6` — verify, don't assume broken
`knowledge-graph/src/knowledge_graph/extraction.py:19` pins `_DEFAULT_MODEL = "claude-sonnet-4-6"`.
The ledger shows `kg,extracted,done`, so this **has resolved successfully** against the
installed `anthropic` SDK at least once — do **not** treat it as a bug. Action: just confirm
it's still the intended model and pin it somewhere configurable (env var / `config.py`)
rather than a module constant, so model bumps don't require a code edit. Low priority.

### B3. `KGStore` imports an unused symbol
`kg_store.py:27` imports `IngestResult` but doesn't use it. Trivial cleanup.

### B4. `VectorIngester` prints to stdout
`vector-db/src/vector_db/ingestion.py` and `vector_store.py` use `print(...)` liberally
alongside `logging`. For a library that's fine as UX but noisy if embedded. Consider routing
through `logging` only. Note `VectorIngester` is **not** on the pipeline path (the button uses
`write_vector`), so this is cosmetic. Low priority.

### B5. `normalize()` vs the plan — this is a DOC issue, not a bug
`ids.py:6` `normalize()` only right-strips lines; `IMPLEMENTATION_PLAN.md §0.2` says
"lowercase-fold for hashing." The code's choice (case-sensitive hashing so case-different
captures stay distinct) is defensible and shipped. **Do not "fix" the code to match the plan.**
Instead, update the plan's `normalize` description to match the shipped behavior (or add a
one-line note that lowercase-folding was intentionally dropped). Filed here only to prevent
someone mistaking it for a code defect.

---

## Tier C — Repo hygiene

The `Database/` root is **not** a git repo (only `Raw Data/` is). Committed/checked-in build
and cache artifacts are cluttering the tree:

### C1. Add a `Database/.gitignore` (and decide on a root repo)
Ignore at minimum:
```
**/.venv/
**/__pycache__/
**/*.pyc
**/.mypy_cache/
**/*.egg-info/
vector-db/build/
vector-db/chroma_store/          # derived, rebuildable from bronze
sqlite/*.db-shm
sqlite/*.db-wal
.DS_Store
```
(`chroma_store/` is explicitly "derived, disposable, rebuildable from bronze" per
`run.py:34` — safe to ignore/regenerate.)

### C2. Delete stale build/cache artifacts already in the tree
- `vector-db/build/lib/vector_db/` — stale duplicate of `src/vector_db/` from an old build. Delete.
- `knowledge-graph/src/knowledge_graph.egg-info/` and `vector-db/src/vector_db.egg-info/` — regenerable. Delete + ignore.
- All `__pycache__/`, `.mypy_cache/` — regenerable. Delete + ignore.
- `.DS_Store` files. Delete + ignore.

### C3. Consolidate scattered verification/backup artifacts under `sqlite/`
`sqlite/_verification/`, `sqlite/_verification_artifacts.db(-shm/-wal)`, and
`sqlite/backups/*.db` are test/backup leftovers. Confirm they're not referenced by any code
(`grep -rn "_verification"` — expected: none), then move to a single ignored `sqlite/_scratch/`
or delete. **Keep `podcast_pipeline.db` and `ledger.db`.**

### C4. `Raw Data/` is its own git repo nested inside `Database/`
Decide intentionally: either make `Database/` the repo (and `Raw Data/` a normal subdir), or
keep `Raw Data/` as a submodule. Right now it's an accidental nested repo, which will confuse
tooling. Not urgent, but flag it.

---

## Tier D — Known gaps (informational — build when ready, not part of "revision")

- **No tests exist**, despite `pytest`/`pytest-cov`/`mypy --strict` configured in both
  `pyproject.toml` dev extras. The core design promise is "recovery path == happy path"
  (idempotent re-runs, extraction reused with zero LLM spend). That promise is currently
  unverified by any automated check. Highest-value net-new work: a few tests over `lib.ledger`
  idempotency, `capture()` dedupe, `chunk_text` determinism, and the `extract_triplets`
  "already-done → no Claude call" branch (mock the client).
- **SQLite consumer (Phase 2.2) is unbuilt.** `ROUTING` lists `"sqlite"` as a target for
  gmail/podcast/article/highlight, but there is no `sqlite_store/run.py`. `TERMINAL_STAGE`
  correctly omits `sqlite` so staleness doesn't nag. This is expected/tracked in
  `IMPLEMENTATION_PLAN.md` and `sqlite/TODO.md` — listed here only for completeness.
- **Phase 1b (Batch API) and Phase 3 (backup/rebuild scripts)** remain per the plan.
  `Raw Data/backups/dump_ledger.sh` exists; `backups/dump_sqlite.sh` / `backups/rebuild_kg.py`
  do not. Not blocking.

---

## Suggested order of execution for Codex

1. **Tier C** first (hygiene) — mechanical, low-risk, makes the diff for later steps clean.
2. **Tier A** (docs) — the main event. Do the disposition table top-to-bottom; finish with A3's grep to prove no lies remain.
3. **Tier B** — only after confirming each item against the live code; all optional.
4. **Tier D** — separate future work; do not bundle into this revision.
