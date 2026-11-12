# knowledge_graph — Coding Guide for Claude

**Last updated:** 2026-07-05

`knowledge_graph` is the **KG consumer** of the Raw Data storage pipeline. It reads bronze
items routed to `kg` from the shared ledger, extracts `(subject, relation, object)` triplets
with Claude, and MERGEs them into Neo4j as `:Concept` nodes and `:KG_EDGE` relationships.

> **This package has nothing to do with `study_system`, FSRS, quizzes, or a CFA study app.**
> Older docs described a "KG + Vec DB + study system" monorepo — that architecture is not in
> this tree. If you find a doc claiming otherwise, it is stale; trust the code and this file.

## Read these first

- **`../../Constitution/STORAGE_PRINCIPLES.md`** — the authoritative principles
  (`P1`, `P4`, `P6`, `P11`… markers in the code point here).
- **`../WORKFLOW.md`** (top level) — the accurate end-to-end trace of the whole pipeline
  (capture → bronze → ledger → kg/vector consumers).
- **`../IMPLEMENTATION_PLAN.md`** — build plan + the reconciliation table (shipped names win).

## Layout

```
knowledge-graph/
├── pyproject.toml                 knowledge_graph package (neo4j core; anthropic optional [extraction])
├── KG_NEW.md                      historical build plan for this slice (see banner in the file)
└── src/knowledge_graph/
    ├── run.py         run_kg(): pending("kg","written") loop, the button's entry point
    ├── extraction.py  extract_triplets(item): bronze → Claude → triplets JSONL, idempotent
    ├── ingestion.py   write_kg(item, path, store): UNWIND MERGE triplets into Neo4j
    ├── kg_store.py    KGStore: Neo4j driver, upsert/read API, opt-in cycle detection
    ├── models.py      KGNode, KGEdge, Triplet, GraphHit (+ relation-string constants)
    ├── prompts.py     EXTRACT_TRIPLETS prompt + retry suffix
    └── kg_store.md    technical reference for kg_store.py
```

## How it runs (the button)

```bash
cd knowledge-graph
RAW_DATA_ROOT="$(cd ../'Raw Data' && pwd)" \
PYTHONPATH="$PWD/src" \
.venv/bin/python -m knowledge_graph.run
```

`run_kg()` adds `RAW_DATA_ROOT` to `sys.path` so it can import the shared core (`lib.ledger`,
`lib.heartbeat`, `lib.bronze`) from `../Raw Data/lib`. There is **no** package dependency on
`lib`; it is resolved at runtime via that path shim. Neo4j connection comes from `NEO4J_*`
env vars (defaults `bolt://localhost:7687`, `neo4j`/`neo4j`).

## Rules that matter here

- **Idempotency is the whole design.** Extraction is skipped when `(kg, extracted)` is already
  `done` (reuses the JSONL, **zero Claude spend**); the Cypher MERGEs on
  `(subject_id, relation, object_id)` so re-writes never duplicate. The recovery path and the
  happy path are identical — don't add logic that breaks that.
- **Bronze is read verbatim** via `lib.bronze.read_body` (P1). Never read a cleaned/spellchecked copy.
- **Failures are recorded, not swallowed.** Each step marks `(kg, <stage>, failed, error=…)` and
  re-raises; `run_kg`'s per-item try/except counts it and moves on.
- **Cycle detection is dormant.** `KGStore` supports it via `hierarchical_relations`, but the
  pipeline builds `KGStore()` without it and writes through `execute_write`, bypassing it. Leave
  it opt-in unless you deliberately wire it in.

## The generic library surface

`KGStore` and the `models` types are also a standalone graph API (read methods `neighbors`,
`reachable`, `edges_for_node`, `search_by_name`, etc.) with no in-repo caller. Keep it usable by
external consumers, but the pipeline path is `run_kg → extract_triplets → write_kg`.
