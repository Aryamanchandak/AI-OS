# Workspace — Coding Guide for Claude

**Last updated:** 2026-06-22
**Three installable Python packages live here. Read this file first, then the per-package `CLAUDE.md`.**

---

## Folder Structure

```
KG + Vec DB + study system/
├── CLAUDE.md                  ← you are here (router + install order + cross-cutting rules)
│
├── study-system/              ← PACKAGE: study_system (CFA L1 study app — ingest, FSRS, quiz, CLI)
│   ├── CLAUDE.md              ← full study-system reference
│   ├── README.md, OVERVIEW.md, TODO.md
│   ├── pyproject.toml
│   ├── src/study_system/      ← all source code (cli, core, extraction, generation,
│   │                             ingestion, review, scheduling, session, storage,
│   │                             validation, types — shared Pydantic domain types)
│   └── tests/
│
├── knowledge-graph/           ← PACKAGE: knowledge_graph (KG store, cycle detection)
│   └── src/knowledge_graph/   ← kg_store.py (KGStore, CycleDetected), models.py (KGNode, KGEdge)
│
├── vector-db/                 ← PACKAGE: vector_db (ChromaDB-backed similarity store)
│   └── src/vector_db/         ← vector_store.py (VectorStore, SimilarityHit)
│
└── src/                       ← STALE pre-split duplicate of study_system. Do not edit.
                                  Kept only because this mount won't allow deletion —
                                  safe to remove by hand once verified redundant.
```

This was originally one monolithic `study_system` package with `kg/` and `vector/`
subpackages inside it. Both were split out into their own installable packages so the
knowledge graph and vector store can be used/versioned independently of the study app.

---

## Install Order (read this before running anything)

`knowledge_graph` and `vector_db` both import shared domain types from
`study_system.types` (e.g. `RelationType`). `study_system` in turn imports `KGStore`
and `VectorStore` from the other two at runtime (`cli/app.py`, `ingestion/ingester.py`,
`session/director.py`). There's no actual circular *import* at runtime, but there is a
circular *install* dependency — install all three editable, in this order:

```bash
pip install -e ./study-system -e ./knowledge-graph -e ./vector-db
```

study-system's `pyproject.toml` no longer lists `networkx` or `chromadb` as
dependencies — those moved with kg/ and vector/ into their respective packages.

---

## Code Routing — Where to Write New Code

| Working on | Edit files in | Reference doc |
|---|---|---|
| Study app: ingestion, cards, FSRS, Feynman, quiz, CLI | `study-system/src/study_system/` | `study-system/CLAUDE.md` |
| Shared domain types (Card, Concept, Triplet, RelationType, etc.) | `study-system/src/study_system/types/` | `study-system/CLAUDE.md` |
| Knowledge graph store, cycle detection, KGNode/KGEdge | `knowledge-graph/src/knowledge_graph/` | — |
| Vector similarity store | `vector-db/src/vector_db/` | — |
| Study-system tests | `study-system/tests/` | — |

**Rule of thumb:** package-internal behavior lives in that package's own files/docs.
Anything that's a contract *across* packages (the install order above, shared types,
the macOS fork() rule) lives in this file.

---

## Cross-Cutting Constraints

- **No `multiprocessing` with `fork()`.** macOS + OpenAI SDK + Python crashes hard. Use `threading` or `asyncio`. If multiprocessing is genuinely required, set `multiprocessing.set_start_method('spawn')` at the very top of the entry point, before any imports.
- **Errors are conversational, not silent.** Every failure is caught and returned as a user-facing message, not a raw traceback.
- **Don't reach into the stale top-level `src/`.** It's a pre-split duplicate of `study_system`, kept only because this filesystem mount blocks deletion. All real development happens in `study-system/src/`, `knowledge-graph/src/`, and `vector-db/src/`.

---

## What Each Per-Package CLAUDE.md Contains

**`study-system/CLAUDE.md`** — phase status, quick start, project layout, component map, full data flow per CLI command, LLM model split, SQLite schema, module ownership table, integration points (including the knowledge_graph/vector_db boundary), known architectural risks, open items / TODO.

`knowledge-graph/` and `vector-db/` are small enough right now that they don't have their own `CLAUDE.md` — read the source directly (`kg_store.py`, `models.py`, `vector_store.py`).
