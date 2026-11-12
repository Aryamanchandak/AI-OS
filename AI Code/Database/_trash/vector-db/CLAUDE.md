# vector_db — Coding Guide for Claude

**Last updated:** 2026-07-05

`vector_db` is the **vector consumer** of the Raw Data storage pipeline, aligned to the shared
architecture. Design + rationale: **`VECTOR_ALIGNMENT_PLAN.md`** (in this folder).

> Older versions of this file carried a "KG + Vec DB + study system" monorepo router describing
> a `study_system` / FSRS / quiz app and an install order across three packages. **That is stale
> and has been removed.** `vector_db` does **not** import `study_system.types`. Trust the code
> and this file.

## Read first

- **`../../Constitution/STORAGE_PRINCIPLES.md`** — authoritative principles (`P1`, `P4`, `P6`, `P7`, `P11`…).
- **`../WORKFLOW.md`** (top level) — accurate end-to-end pipeline trace.
- **`../IMPLEMENTATION_PLAN.md`** — build plan + reconciliation table.
- **`VECTOR_ALIGNMENT_PLAN.md`** — the vector-consumer design (✅ implemented 2026-07-05).

## Two entry points

1. **Consumer (the button):** `run.py::run_vector()` reads bronze items routed to `vector` from
   the ledger, chunks + embeds + upserts to ChromaDB, records one ledger stage `(vector, upserted)`,
   then fires the staleness heartbeat. Modules: `run.py` (orchestrator), `write.py` (`write_vector`),
   `ingestion.py::chunk_text` (structural, deterministic chunker), `vector_store.py` (`VectorStore`).
2. **Generic library:** `VectorStore` / `VectorIngester` / `IngestDocument` — a standalone
   embed/search API with no domain dependency, used directly by external callers. Do **not**
   change their signatures (see D4 in the plan).

## Run it

The editable `.pth` install is unreliable in these uv venvs, so pass `PYTHONPATH`:

```bash
cd vector-db
RAW_DATA_ROOT="$(cd ../'Raw Data' && pwd)" \
PYTHONPATH="$PWD/src" \
.venv/bin/python -m vector_db.run
# optional: CHROMA_PATH=... (defaults to Database/vector-db/chroma_store)
```

The shared core `lib` (at `../Raw Data/lib`) is resolved by adding `RAW_DATA_ROOT` to `sys.path`
— the same shim `knowledge_graph/run.py` uses. No package dependency on `lib`.

## Write-path safety (P6/P7)

The ingestion path must never let ChromaDB fall back to its default embedder — that silently
writes wrong-dimension vectors and marks them done. `write_vector` calls `store.ensure_embedder()`
before writing and marks `(vector, upserted, failed)` on any error. `assert_writable()` is the
stronger fail-fast (a live Ollama probe) for the start of a run. The read path (`search`) keeps
its graceful no-op behavior.

## Design invariants

- **Bronze read verbatim** (`lib.bronze.read_body`, P1) — never a cleaned copy.
- **Deterministic chunk IDs** `{content_hash}_{i}` and a `content_hash` provenance field on every
  chunk (P4/P6) — the upsert is idempotent by construction. `delete_chunks_by_content_hash` clears
  stragglers before a re-chunk.
- **One ledger stage, `upserted`** (P11) — ChromaDB fuses embed+upsert; nothing expensive is
  persisted, so there's no intermediate artifact to checkpoint.
