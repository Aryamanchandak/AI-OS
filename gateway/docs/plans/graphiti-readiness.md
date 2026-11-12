# Plan: gateway fixes before Graphiti

Date: 2026-10-23. Status: code implemented; offline checks pass; live proof blocked by missing provider setup.

What: close the gateway correctness gaps found in the 2026-10-22 audit, then prove the gateway works on real keys. The Graphiti adapter, live Graphiti schemas and ingest/retrieval proof are later plans, written only after this one passes. Requirements for them are in [graphiti.md](../integrations/graphiti.md), derived from Graphiti 0.31.1 source and not yet checked against an installed copy.

## Fixes

Structured-output repair calls the provider directly, so it skips the concurrency cap, the retry logic and the shared error handling. A provider 400 during repair escapes as an uncaught `ProviderError` instead of a clean HTTP error. Embeddings also bypass the concurrency cap. Both need to go through the same controlled path as normal chat calls, and permanent 4xx errors must stay permanent.

The golden case `zero-session-budget-refuses-before-calling` expects zero ledger rows, but refused requests are recorded by finalization. Update the expectation to the intended behaviour: one row, status refused.

## Approved policy

The retry/repair decision is recorded in [DECISIONS.md](../../DECISIONS.md). Existing ingestion callers request structured output and now receive 502 immediately if it is invalid.

## Done when

Tests cover invalid JSON, schema-validation failure, 400/401/429/5xx, exact attempt counts, unchanged temperature and max tokens, and mixed chat/embed concurrency under the cap. The offline suite and mypy pass. Then the four live golden cases run on real keys and their results are shown to you. That live run is the first end-to-end proof for the gateway, and it comes before any Graphiti work.

## Verification

2026-10-23: offline suite `182 passed, 4 deselected`; mypy `Success: no issues found in 47 source files`. Live golden run, including a rerun with network access: `4 failed, 181 deselected` (before the final dimension-accounting regression test was added). `gateway/.env` is absent, `ANTHROPIC_API_KEY` is unset, and local Ollama is unreachable. Full acceptance remains pending those prerequisites and a passing live rerun.
