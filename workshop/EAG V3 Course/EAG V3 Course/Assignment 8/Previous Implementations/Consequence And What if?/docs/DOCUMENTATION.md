# Documentation map

**Last updated:** 2026-08-24

This page is the starting point for the project documentation. The short README gets the application running; the overview explains what is built and where its limits are; the architecture and orchestration documents explain the structural and runtime views; colocated `*.explained.md` files are the line-level reference for individual source files.

## Start here

| Need | Document |
|---|---|
| Install, run, test, or call the API | [`README.md`](../README.md) |
| Understand the product and current implementation | [`docs/overview/overview.md`](overview/overview.md) |
| Understand boundaries and invariants | [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) |
| Trace a run across files and persisted artifacts | [`deep-dive/orchestration.md`](../deep-dive/orchestration.md) |
| Understand evaluation coverage and live-smoke status | [`docs/EVALUATION.md`](EVALUATION.md) |
| Understand the 2026-08-22 package restructure | [`docs/RESTRUCTURE_RECEIPT.md`](RESTRUCTURE_RECEIPT.md) |

## Per-file reference

Executable package files, focused package tests, prompts, templates, CSS, JavaScript, the launcher, and root test fixtures have colocated companions named `<source>.explained.md`. These companions describe the actual code and its failure modes; they are not imported, packaged, or executed. Start with these high-value references:

- `src/consequence_radar/pipeline/__init__.py.explained.md` for the full pipeline.
- `src/consequence_radar/models/__init__.py.explained.md` for data contracts.
- `src/consequence_radar/graph/__init__.py.explained.md` for graph validation and patching.
- `src/consequence_radar/storage/__init__.py.explained.md` for persistent state.
- `src/consequence_radar/providers/model/__init__.py.explained.md`, `fetch/__init__.py.explained.md`, and `search/__init__.py.explained.md` for external boundaries.
- `src/consequence_radar/web/app.py.explained.md` for HTTP routes, background work, and SSE.

Cross-component tests under `tests/integration/`, `tests/unit/`, and `tests/evaluation/` do not each have a companion file. Their system-level guarantees and omissions are documented in `docs/EVALUATION.md`, while focused tests colocated in package folders do have companions. Generated `__pycache__`, `.pytest_cache`, `.venv`, `uv.lock`, SQLite data, and sample output are intentionally not documented line by line.

## Documentation status and truth hierarchy

The documentation was checked against the source on 2026-08-24. When documents disagree, use this order: current source code, tests, `.env.example` and `pyproject.toml`, then explanatory prose. The live Gemini path is still not credential-smoke-tested; the offline suite is evidence for local contracts and mocked orchestration, not proof of production model quality.

One known source defect remains intentionally documented rather than silently corrected: `graph.apply_patch()` imports assumption and estimate classes from the nonexistent `consequence_radar.graph.models` module at L99–110. See the overview's Known Issues section and the graph companion document before relying on patches that add or update those objects.
