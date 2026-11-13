# Consequence Radar architecture

## Boundaries

Each pipeline stage lives in its own folder under `src/consequence_radar/` — source, unit tests, and any LLM prompt it uses sit together (e.g. `cases/` holds `cases.py`'s logic, `test_cases.py`, and `case_selector.md`). Cross-component regression and integration tests remain in `tests/`.

The `pipeline` package is synchronous, framework-neutral orchestration. It imports neither FastAPI nor templates. The FastAPI shell owns HTTP, a bounded worker pool [WHAT DOES THIS ACTUALLY MEAN ?], persisted progress events [AGAIN HOW AND WHAT?], rendering, and exports. Provider protocols isolate model, grounded search, and page fetching. Tests inject fakes at those boundaries.

SQLite is the durable source of truth. The repository uses an append-oriented artifact table so a new version never overwrites the only copy of a graph, report draft, or rejected patch [WHAT DOES THIS MEAN ? AND HOW DOES IT DO IT ?]. Typed Pydantic models are the canonical vocabulary at every model boundary.

## State machine

```text
queued
  → pre_reading → selecting → building_graph
  → researching (gap → tasks → retrieve → claims → patch → validate) × bounded
  → quantifying → whole-graph review
  → challenging → adjudicating
  → compiling_context → writing_report
  → completed | completed_with_warnings
                         ↘ report_validation_failed
Any fatal stage ─────────────────────────→ failed
```

Every external call checks the model-call and wall-time ledger first. Search queries, source attempts, tasks per cycle, cycles, nodes, edges, redirects, response bytes, retries, and worker concurrency are independently bounded [ARE ALL OF THESE REALLY NECESSARY ?].

## Canonical graph memory

The graph contains typed nodes, directed causal edges, material assumptions, estimates, and feedback warnings. Edges separately link supporting claims, contradicting claims, assumptions, and estimates. Active topology must have one news seed, valid endpoints, no cycles, no orphan outcomes, mechanisms on every edge, and a specific path to an Indian company/sector/market metric. A terminal path must contain a sourced/derived or explicit directional estimate. A direct news-to-stock-price leap is invalid.

Models return patch operations. Local code applies them to a deep copy, validates the candidate, then commits a new graph version. A malformed patch gets one structured repair request; if repair also fails, the last valid graph remains canonical and both rejected attempts remain in the audit ledger.

## Evidence and estimates

The model extracts atomic claim drafts from bounded source excerpts. Local normalized-substring matching is authoritative: an absent exact passage produces a rejected-claim record. Facts, forecasts, assumptions, estimates, and inferences remain separate types.

Decimal calculations expose formulas and input IDs. Currency conversions preserve the original estimate and add a separate derived record. Unavailable coefficients produce `directional_only` plus a caveat rather than an invented number. The quantification validator ensures every Indian terminal is linked to an attempted estimate.

## Disproof and cases

The challenger sees the complete graph, evidence, assumptions, estimates, endpoints, and research failures. Findings target named IDs. One separate adjudication returns a decision and operations for each accepted finding; there is no critic/adjudicator conversation. Case selection then requires one coherent active central path, rejects an all-assumption path, and permits alternatives only when a material assumption changes the result.

## Report boundary

The deterministic compiler topologically orders the final graph and selects accepted analytical state—not raw page text. If over budget, it first removes non-load-bearing background claims and their unused sources. It never removes central evidence or assumptions; remaining overflow is fatal.

The writer receives that one context and returns a structured report in one normal call. Deterministic checks enforce word bounds, known `[S…]` markers, valid source IDs, exact graph assumption strings, substantive fields, and prohibited instruction language. Invalid drafts are stored but never published through the validated report endpoint.

## HTTP and UI

The API creates a run with `202`, exposes status, persisted SSE events, report, graph, audit, and downloads. The editorial UI renders the report first, then central case/assumptions, candidate ranking, graph, estimates, and audit. Earlier successful runs remain in persistent history when a newer run fails.