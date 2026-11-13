# `pipeline/__init__.py`

This is the top-level orchestrator: a single `Pipeline` class whose `run(run_id, progress)` method calls every other stage of the system in a fixed sequence, threading state (graph, claims, sources, gaps, failures) between them, persisting an artifact after each stage, and translating any exception into a `FAILED` run rather than letting it propagate. This is the one file that shows the whole system wired together end to end.

## Construction

`Pipeline.__init__(settings, repository, *, model=None, search=None, fetcher=None)` builds:
- `self.ledger = UsageLedger(settings.max_model_calls_per_run, settings.max_wall_time_seconds, settings.max_search_queries_per_run)` — the shared budget tracker (see `metering/__init__.py`; documented further in `test_budget.py.explained.md`).
- `self.model = model or GeminiModelClient(settings, self.ledger, on_call=self._record_model_call)` — every real model call goes through the ledger and, via `on_call`, gets persisted as a `model_call` artifact keyed by a freshly minted `"M" + uuid4().hex[:10]` id (`_record_model_call`, only fires while `self._active_run_id` is set).
- `self.search = search or GeminiGoogleSearchProvider(settings, self.ledger, on_call=self._record_model_call, run_id_getter=lambda: self._active_run_id)` — same ledger, same audit sink.
- `self.fetcher = fetcher or PageFetcher(settings)`.
- All three defaults are dependency-injectable, which is how `test_budget.py` constructs a `Pipeline` with `model=object(), search=object(), fetcher=object()` purely to inspect `pipeline.ledger` without making real calls.

## The call sequence inside `run()`

Everything happens inside one `try/except Exception/finally` block. `self._active_run_id` is set before the try and cleared to `None` in `finally`, so model-call auditing only happens during an active run. On any exception, the `except` branch saves a `usage` artifact from `self.ledger.snapshot()`, sets the run status to `RunStatus.FAILED` with the exception's string as the error, and logs a `"failed"` event — no re-raise, so `run()` never throws to its caller.

The literal order of stage calls, with the sibling module each comes from:

1. **`normalize_batch(NewsBatch.model_validate(run["batch"]))`** — `..ingest`. Saved as artifact `normalized_batch`.
2. **`self._stage(run_id, RunStatus.PRE_READING, ...)`** — sets status, logs event, calls `progress()`, and calls `self.ledger.guard_time()` (every `_stage` call is also a wall-clock budget checkpoint).
3. **`pre_read(batch, self.fetcher, guard=self.ledger.guard_time)`** — `..ingest`. Saved as `discovery_extracts`.
4. **`deduplicate(extracts)`** — `..deduplicate`. Saved as `dedup_groups`.
5. **`_stage(..., RunStatus.SELECTING, ...)`**
6. **`select_candidate(run_id, extracts, groups, self.model)`** — `..select`. A model call (this is the `"candidate_selection"` stage referenced by `test_budget.py`'s `ONE_OFF` tuple). Returns a list of candidates; saved as `candidates`. The pipeline then does `seed = next(c for c in candidates if c.selected)` — if `select_candidate` ever returns a list with no candidate marked `selected`, this raises `StopIteration`, uncaught by anything specific, falling through to the outer `except Exception` and failing the run with that raw `StopIteration` as the error message.
7. **`_stage(..., RunStatus.BUILDING_GRAPH, ...)`**
8. **`build_initial_graph(run_id, seed, self.model, self.settings)`** — `..graph`. One (or two, if repaired) model calls (`"initial_graph"` / `"initial_graph_repair"`). Saved as `graph` at `version=1`.
9. **Research loop**, up to `settings.max_research_cycles` (default 3) iterations, entered under `_stage(..., RunStatus.RESEARCHING, ...)`. Each cycle:
   - `generate_tasks(run_id, graph, self.model, self.settings)` — `..research`. If empty, the loop breaks immediately (no more gaps to research).
   - `retrieve_for_tasks(tasks, self.search, self.fetcher, self.settings, counters, guard=self.ledger.guard_time)` — `..research`; `counters` (`{"queries": 0, "sources": 0}`) is threaded through and mutated across cycles, so per-cycle limits (e.g. `max_research_tasks_per_cycle`) are enforced cumulatively by whatever logic lives inside `retrieve_for_tasks` itself, not visible in this file.
   - `extract_claims(run_id, tasks, sources, self.model, len(all_claims) + 1)` — `..research`. `start` id offset keeps claim ids globally unique across cycles.
   - The patch step is done **inline in this file**, not via a `graph` module function: `self.model.generate(run_id=run_id, stage="graph_patch", prompt_name="graph/graph_patcher.md", prompt_data=json.dumps({"graph": ..., "tasks": ..., "claims": ...}), schema=GraphPatch, model_tier="reasoning")`. The result is applied with `graph.apply_patch(graph, patch, self.settings)`.
   - On any exception from `apply_patch` (validation failure *or* the assumption/estimate import bug documented in `graph/__init__.py.explained.md`), the pipeline logs `invalid_graph_patch` and issues **one** repair call (`stage="graph_patch_repair"`, `retry_count=1`), passing `rejected_patch`, `validation_errors` (via `getattr(exc, "problems", [str(exc)])` — so a non-`GraphValidationError` exception, like the import bug, is stringified into a one-element list rather than a real problem list), and the same claims. If the repair also fails to apply, it's logged as `invalid_graph_patch` with key `cycle-{cycle}-repair` and **the cycle silently ends with the graph unchanged** — no exception propagates.
   - `gaps = applied_patch.remaining_gaps` — note `applied_patch` is only reassigned to the repair patch if the repair *succeeded*; if both the original patch and its repair failed to apply, `applied_patch` is still the original (never-applied) patch object, so `gaps` reflects a patch that was never actually merged into the graph. The loop breaks when `gaps` is empty.
10. **`_stage(..., RunStatus.QUANTIFYING, ...)`**
11. `validate_graph(graph, self.settings, require_indian_path=True, claim_ids={c.id for c in all_claims})` — `..graph`. This is the first point in the run where the India-reachability and claim-integrity rules are enforced.
12. If any error string contains `"no quantified or directional estimate"`: one more inline `graph_patcher.md` call, `stage="quantification_patch"`, with a synthetic `"instruction"` key in the payload instead of tasks (see `graph_patcher.md.explained.md`). The resulting patch is applied with **no try/except** — a failure here raises straight out to the outer handler and fails the run. The revision-log call fabricates a fake "before" graph via `graph.model_copy(update={"version": graph.version - 1})` purely so `_save_revision` has something with a `.version` one lower than the real `after` graph — this is a shortcut, not the actual pre-patch object (which was already overwritten in place by `apply_patch`'s return value). Errors are then rechecked.
13. If `endpoint_errors` are still non-empty after that, `raise ValueError("; ".join(endpoint_errors))` — fails the run.
14. **`whole_graph_review(run_id, graph, all_claims, self.model)`** — `..challenge`. One model call (`"whole_graph_review"`). If it returns any operations, they're applied via `graph.apply_patch(..., require_indian_path=True)` and logged as a revision.
15. **`_stage(..., RunStatus.CHALLENGING, ...)`**
16. **`challenge(run_id, graph, all_claims, failures, self.model)`** — `..challenge`. One model call (`"challenge"`). Saved as artifact `challenge`.
17. **`_stage(..., RunStatus.ADJUDICATING, ...)`**
18. **`adjudicate(run_id, graph, findings, all_claims, self.model, self.settings)`** — `..challenge`. One model call (`"adjudication"`). Returns `(graph, decisions)`; note `adjudicate` itself imports and calls `apply_patch` internally (confirmed via `challenge/__init__.py`'s own `from ..graph import apply_patch`), so the graph mutation for accepted challenge findings happens *inside* `challenge.adjudicate`, not via a second call from this file. The pipeline only reconstructs a synthetic `GraphPatch` afterward (from `decision.operations` where `decision.decision.startswith("accept_")`) purely to write a `GraphRevision` audit record — it does not re-apply anything.
19. `validate_graph(..., require_indian_path=True, claim_ids=...)` again — final check; failure raises `ValueError` and fails the run.
20. Saves `adjudication` artifact, and as a defensive fallback saves the `graph` artifact again if `repo.artifact(run_id, "graph", version=graph.version)` doesn't already exist (guards against `adjudicate`'s internal patch producing a new graph version that was never separately persisted).
21. **`select_cases(run_id, graph, all_claims, self.model)`** — `..cases`. One model call (`"case_selection"`). Saved as `cases`.
22. **`_stage(..., RunStatus.COMPILING_CONTEXT, ...)`**
23. **`compile_context(seed=seed, graph=graph, cases=cases, claims=all_claims, sources=all_sources, findings=findings.findings, decisions=decisions.decisions, gaps=gaps, failures=failures, token_budget=self.settings.report_context_token_budget)`** — `..report_context`. Pure/no model call; internally calls `topological_graph` (from `..graph`) to reorder nodes. Saved as `report_context`.
24. **`_stage(..., RunStatus.WRITING_REPORT, ...)`**
25. **`write_report(run_id, context, self.model, self.settings.report_min_words, self.settings.report_max_words)`** — `..report`. One model call (`"newsletter"`), returns `(report, errors)`. Saved as `report_draft` if `errors` else `report`, plus a separate `report_validation` artifact.
26. Saves final `usage` snapshot from `self.ledger`.
27. Sets terminal status: `REPORT_VALIDATION_FAILED` if the report failed word-count/content validation; otherwise `COMPLETED_WITH_WARNINGS` if `failures` (research fetch failures) or `rejected_claims` is non-empty, else plain `COMPLETED`.

### Sibling packages imported but never called directly

The task brief expected `evidence` and `quantify` subpackages to appear here (both exist as directories under `src/consequence_radar/`), but neither is imported by `pipeline/__init__.py`. Claim extraction and research retrieval both come from `..research` (`extract_claims`, `generate_tasks`, `retrieve_for_tasks`), and the "quantify" gap-filling step is done inline via a `graph_patcher.md` call (`stage="quantification_patch"`) rather than by calling into a `quantify` module function. Whatever those two directories contain, it is not wired into the orchestrator's visible call graph — either they're consumed by one of the sibling packages this file does import (e.g. `research` or `challenge` internally), or they're currently dead/unused from the top-level pipeline's perspective. This wasn't traced further since it falls outside `pipeline/__init__.py` itself.

### RunStatus values touched

In order emitted by `_stage`/`set_status` calls in this file: `PRE_READING → SELECTING → BUILDING_GRAPH → RESEARCHING → QUANTIFYING → CHALLENGING → ADJUDICATING → COMPILING_CONTEXT → WRITING_REPORT →` one of `{COMPLETED, COMPLETED_WITH_WARNINGS, REPORT_VALIDATION_FAILED, FAILED}`. `RunStatus.QUEUED` exists in `models/__init__.py` but is never set from this file — it must be the status a run is created with before `Pipeline.run()` is ever invoked, elsewhere in the system (not shown here).

## Non-obvious logic / hacks worth knowing

- `_record_model_call` mints a fresh `model_call` artifact id on every callback but only stores the *most recent* one in `self._last_model_call_id`; `_save_revision` attaches whatever that value currently is to the `GraphRevision.model_call_id`, so it is correct only because each patch-generating model call is immediately followed by its own `_save_revision` before any other model call happens — this is an implicit ordering dependency, not something enforced by the types.
- The generation-budget stage names implied by `test_budget.py` (`"gap_analysis"`, `"claim_extraction"`, `"graph_patch"`, `"graph_patch_repair"`, `"candidate_selection"`, `"initial_graph"`, `"quantification_patch"`, `"whole_graph_review"`, `"challenge"`, `"adjudication"`, `"case_selection"`, `"newsletter"`) line up with the `stage=` labels visible in this file and inferred from imported functions, **except** `"initial_graph_repair"`, which is a real, budget-consuming call this file can trigger (via `graph.build_initial_graph`'s internal repair) but which the budget model in `test_budget.py`'s `ONE_OFF` tuple does not count — see `test_budget.py.explained.md`.
- The research loop's per-cycle budget (`max_research_tasks_per_cycle`, `max_search_queries_per_run`) is enforced somewhere inside `retrieve_for_tasks`/the search provider, not in this file; this file only threads the shared mutable `counters` dict through.
- Every `_stage` call re-checks the wall-clock budget (`self.ledger.guard_time()`), so a run can fail mid-pipeline with `BudgetExceeded` at any stage transition even if no single model call was slow.

## Connections

Imports, in file order: `..cases.select_cases`; `..challenge.adjudicate, .challenge, .whole_graph_review`; `..config.Settings`; `..graph.GraphPatch, .apply_patch, .build_initial_graph, .validate_graph`; `..ingest.normalize_batch, .pre_read`; `..deduplicate.deduplicate`; `..metering.UsageLedger`; `..models.GraphRevision, .NewsBatch, .RunStatus`; `..providers.fetch.PageFetcher`; `..providers.model.GeminiModelClient, .ModelClient`; `..providers.search.GeminiGoogleSearchProvider, .SearchProvider`; `..report.write_report`; `..report_context.compile_context`; `..research.extract_claims, .generate_tasks, .retrieve_for_tasks`; `..select.select_candidate`; `..storage.Repository`. `test_budget.py` imports `Pipeline` directly to inspect ledger wiring without running it.
