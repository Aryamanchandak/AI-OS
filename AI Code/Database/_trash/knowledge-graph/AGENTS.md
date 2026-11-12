# knowledge_graph — Coding Guide for Codex

**Last updated:** 2026-07-05

Same content as `CLAUDE.md` in this folder — read that for the full guide. Summary:

`knowledge_graph` is the **KG consumer** of the Raw Data storage pipeline: bronze items routed
to `kg` → Claude triplet extraction → Neo4j `:Concept`/`:KG_EDGE` MERGE.

> **Not** a `study_system` / FSRS / quiz / CFA app. Any doc saying so is stale — trust the code.

Read first:
- `../../Constitution/STORAGE_PRINCIPLES.md` — authoritative principles (`P1`, `P4`, `P6`, `P11`…).
- `../WORKFLOW.md` (top level) — accurate end-to-end pipeline trace.
- `../IMPLEMENTATION_PLAN.md` — build plan + reconciliation table.

Entry point (the button):
```bash
cd knowledge-graph
RAW_DATA_ROOT="$(cd ../'Raw Data' && pwd)" PYTHONPATH="$PWD/src" \
  .venv/bin/python -m knowledge_graph.run
```

Pipeline path: `run.py::run_kg` → `extraction.py::extract_triplets` (idempotent, reuses JSONL with
zero Claude spend when already extracted) → `ingestion.py::write_kg` (UNWIND MERGE, idempotent on
`(subject_id, relation, object_id)`). Shared core `lib.*` is imported from `../Raw Data/lib` via a
`sys.path` shim (`RAW_DATA_ROOT`), not a package dependency. Failures mark
`(kg, <stage>, failed, error=…)` and re-raise. Cycle detection exists but is dormant on the live path.
