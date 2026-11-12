# vector_db — Coding Guide for Codex

**Last updated:** 2026-07-05

Same content as `CLAUDE.md` in this folder — read that for the full guide. Summary:

`vector_db` is the **vector consumer** of the Raw Data storage pipeline: bronze items routed to
`vector` → structural chunking → local Ollama (`nomic-embed-text`) embeddings → ChromaDB upsert,
recording one ledger stage `(vector, upserted)`.

> **Not** a `study_system` / FSRS / quiz / CFA app, and it does **not** import `study_system.types`.
> Any doc saying so is stale — trust the code.

Read first:
- `../../Constitution/STORAGE_PRINCIPLES.md` — authoritative principles (`P1`, `P4`, `P6`, `P7`, `P11`…).
- `../WORKFLOW.md` (top level) — accurate end-to-end pipeline trace.
- `VECTOR_ALIGNMENT_PLAN.md` — the vector-consumer design (✅ implemented 2026-07-05).

Entry point (the button):
```bash
cd vector-db
RAW_DATA_ROOT="$(cd ../'Raw Data' && pwd)" PYTHONPATH="$PWD/src" \
  .venv/bin/python -m vector_db.run
# optional: CHROMA_PATH=... (defaults to Database/vector-db/chroma_store)
```

Two entry points: (1) the consumer `run.py::run_vector` → `write.py::write_vector` →
`ingestion.py::chunk_text` → `vector_store.py::VectorStore`; (2) the generic library
`VectorStore`/`VectorIngester`/`IngestDocument` — **do not change their signatures**. Shared core
`lib.*` is imported from `../Raw Data/lib` via a `sys.path` shim (`RAW_DATA_ROOT`), not a package
dependency. Write-path safety (P6/P7): `write_vector` calls `ensure_embedder()` before writing so
ChromaDB never silently falls back to a wrong embedder; failures mark `(vector, upserted, failed)`.
Chunk IDs are deterministic (`{content_hash}_{i}`) and every chunk carries `content_hash` for provenance.
