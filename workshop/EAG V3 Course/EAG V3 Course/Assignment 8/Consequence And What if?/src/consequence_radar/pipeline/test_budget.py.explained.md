# `pipeline/test_budget.py`

Not a pipeline-behavior test — it's a consistency check between the *configured* budget ceilings in `Settings` and a hand-built model of how many LLM generations, search queries, and seconds a full worst-case run of `Pipeline.run()` actually needs. Its purpose (per its module docstring) is to catch the specific failure mode where someone tightens a default in `config/__init__.py` and silently makes every real run die partway through from `BudgetExceeded` (`metering/__init__.py`).

## The budget model it builds

```python
PER_CYCLE = ("gap_analysis", "claim_extraction", "graph_patch", "graph_patch_repair")
ONE_OFF = ("candidate_selection", "initial_graph", "quantification_patch",
           "whole_graph_review", "challenge", "adjudication", "case_selection", "newsletter")

def worst_case_generations(settings):
    return len(ONE_OFF) + settings.max_research_cycles * len(PER_CYCLE)
```

`ONE_OFF` (8 stages) counts every model-generating call `pipeline/__init__.py` makes outside the research loop. `PER_CYCLE` (4 stages) counts every model-generating call made once per research-loop iteration, multiplied by `settings.max_research_cycles` (default 3), assuming the absolute worst case where every cycle needs its `graph_patch_repair` fallback. With defaults this is `8 + 3*4 = 20`.

Cross-referencing against `pipeline/__init__.py`, `PER_CYCLE`'s four names line up with: `generate_tasks` (`..research`, presumably tagged `"gap_analysis"` internally — not directly visible in `pipeline/__init__.py`), `extract_claims` (`..research`), and the inline `stage="graph_patch"` / `stage="graph_patch_repair"` calls this file makes directly. `ONE_OFF`'s eight names line up one-to-one with `select_candidate`, `build_initial_graph`'s primary call (`stage="initial_graph"`), the inline `stage="quantification_patch"` call, `whole_graph_review`, `challenge`, `adjudicate`, `select_cases`, and `write_report`.

**Gap this test's model doesn't cover:** `build_initial_graph` (`graph/__init__.py`) can itself issue a second call tagged `stage="initial_graph_repair"` when the first graph fails validation. That call is real, budget-consuming, and not represented anywhere in `ONE_OFF` or `PER_CYCLE` — so `worst_case_generations()` can undercount an actual worst-case run by at least one generation. The test as written would still pass even though the true worst case exceeds its model, because `max_model_calls_per_run` (45 by default) has enough slack above the computed 20 to absorb it — but the assumption is not verified anywhere.

## The three assertions

- **`test_default_generation_budget_covers_a_worst_case_run`**: builds `Settings(_env_file=None)` (defaults, `.env` explicitly not loaded) and asserts `settings.max_model_calls_per_run >= worst_case_generations(settings)` — i.e. the generation ceiling (default 45) must be able to cover the worst-case 20 calls the model predicts, with the failure message spelling out exactly how many are needed vs. budgeted if it ever regresses.
- **`test_searches_are_not_charged_against_the_generation_budget`**: first asserts `settings.max_search_queries_per_run + worst_case_generations(settings) > settings.max_model_calls_per_run` (30 + 20 = 50 > 45) — this is a proof-by-construction that *if* searches and generations shared one counter, a full run would starve itself of generation calls before finishing, which is exactly why `UsageLedger` (`metering/__init__.py`) tracks `_calls` (`guard_external_call(kind="model")`) and `_searches` (`kind="search"`) as two independent counters against two independent ceilings. It then builds a real `Pipeline` with a throwaway sqlite `Repository` and stub `model=object(), search=object(), fetcher=object()` (never actually called — the test only inspects wiring, not behavior) and asserts `pipeline.ledger.max_calls == settings.max_model_calls_per_run` and `pipeline.ledger.max_searches == settings.max_search_queries_per_run`, confirming `Pipeline.__init__` actually passes these two settings fields into the ledger correctly rather than, say, swapping them or defaulting one from the other (`UsageLedger.__init__` does default `max_searches` to `max_calls` when `None` is passed — this test guards against that default silently kicking in when it shouldn't).
- **`test_wall_clock_allows_a_reasoning_tier_run`**: asserts `settings.max_wall_time_seconds >= worst_case_generations(settings) * 30` (1800 >= 20*30 = 600) — a coarse per-call budget of 30 seconds, chosen because reasoning-tier Gemini calls dominate wall-clock time and search/fetch latency has to fit in the same window; this is a sanity floor, not a tight bound.

## Why this matters

Every assertion here is a static arithmetic check against `Settings` defaults — none of them execute `Pipeline.run()`. They exist purely to keep the three independent budget knobs (`max_model_calls_per_run`, `max_search_queries_per_run`, `max_wall_time_seconds`) in `config/__init__.py` honest against the actual shape of a run traced through `pipeline/__init__.py`, and they will only catch a regression if `PER_CYCLE`/`ONE_OFF` are kept in sync by hand whenever a new model call is added to the pipeline (as the `initial_graph_repair` gap above demonstrates, that sync is not currently perfect).
