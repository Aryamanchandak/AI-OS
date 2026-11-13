# Evaluation and hardening

## Philosophy

Evaluation measures traceability, causal usefulness, visible assumptions, Indian-equity specificity, estimate integrity, counterevidence handling, and resistance to hindsight. It does not score whether the application predicted a later market outcome.

Five frozen-date batches live in `tests/fixtures/evaluation_batches.json`. Each fixture records duplicates, an acceptable winner and alternatives, expected transmission, unsupported leaps, quantities available at the simulated date, and dated evidence metadata. The evaluation test rejects any source dated after its cutoff.

## Offline gates

- URL canonicalisation, SSRF rejection, redirects, type and byte bounds.
- Conservative de-duplication and factual-status handling.
- DAG, IDs, endpoints, references, Indian path, concrete terminal and estimate attempt.
- Patch rollback and one repair path.
- Exact-passage acceptance/rejection.
- Decimal formulas, ranges, FX conversion lineage, and sensitivity.
- Central path and material-alternative rules.
- Context reduction and fatal overflow.
- Citation and investment-instruction validation.
- Model/wall-time budgets.
- Successful, repaired-graph, no-candidate, bad-citation, and restart-persistence integrations.
- Prompt-injection fixture remains data and does not alter stage instructions.

Run with `./radar test`.

## Live smoke record

Status: **not run — no live credential was available during implementation**.

When credentials are supplied, append:

```text
Date/time:
Git revision:
Run ID:
FAST_MODEL / REASONING_MODEL / REPORT_MODEL:
Terminal state:
Calls / input tokens / output tokens / elapsed:
Fetched sources / rejected claims:
Graph versions:
Report word count:
Citation validation:
Warnings:
Reviewer notes:
```

Use `samples/input_batch.json`, keep the returned exported JSON, and do not substitute later evidence into the frozen evaluation score.
