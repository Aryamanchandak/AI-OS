# `report_context/test_report_context.py`

One test, `test_context_compiles_and_enforces_token_budget`, exercising `compile_context` at both ends of the budget behavior. Uses the shared `graph` fixture from the project-root `conftest.py` (three nodes N0-N2, two edges E1-E2, one assumption A1, one estimate Q1 — see that file for exact values).

Builds a minimal but complete input set: a `CandidateSeed`, a single verified supporting `EvidenceClaim` (`C1`, from source `S1`), a matching `SourceRecord`, and a `CaseSelection` wrapping a hand-built central `Case` ("Cost compression", path N0→N1→N2 via E1/E2, requiring assumption A1, citing claim C1 and estimate Q1). Findings/decisions/gaps/failures are all passed empty.

Two assertions: with `token_budget=10000` the call succeeds and the resulting context has non-empty `sources` and `assumptions` (confirming the basic assembly and source-filtering/assumption-filtering logic actually populate those fields rather than defaulting to empty); with `token_budget=1`, the same call raises `ContextBudgetError` — confirming the hard-fail path when even the load-bearing-only trimmed context can't fit.

This is a thin integration test — it doesn't isolate the intermediate "trim non-load-bearing claims and retry" path (with `token_budget=1`, nothing fits even after trimming, so it goes straight to the exception without proving the middle step behaves correctly on its own), and it doesn't assert on excerpt lengths, claim/source counts precisely, or the `min-not-max` edge case around the budget boundary.
