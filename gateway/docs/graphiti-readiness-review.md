# Review: graphiti-readiness plan

Date: 2026-10-24. Scope: checked the code against [graphiti-readiness.md](plans/graphiti-readiness.md). Delete this file once the points below are resolved.

## Result

The code matches the plan. I reran the offline suite (182 passed, 4 deselected) and `mypy src` (clean). Chat and embeddings now share one controlled path for the concurrency cap and retries, permanent 4xx errors stop immediately, and the refused-budget golden case now expects one ledger row with status `refused`. The plan is not fully accepted yet because the live golden run has not happened.

## What you should know

The plan's "Fixes" paragraph is out of date. It says repair calls should go through the controlled path, but the code removed repair entirely, which is what the "Approved policy" section says. The paragraph should be reworded to match.

Two changes go beyond the brief. The Anthropic "thinking" 400-fallback was removed (it is in DECISIONS.md but not in the plan). And a request with `json_object` and no schema now returns 502 if the JSON is invalid; before, it was never checked. Three unused helpers were also deleted from `providers/base.py`; I could not fully confirm nothing else uses them, because my grep failed.

The working tree has unrelated changes that should stay out of the commit: `shell/package.json`, `simple_llm/`, `../workshop/Old Code/` and the two Graphiti docs under `../Ingestion 2/`.

The plan says mypy checked "47 source files" with no issues. `mypy src` checks 46. Including `tests` it checks 47 and finds one error, a missing return type at `tests/conftest.py:18`.

## What is blocking acceptance

There is no `gateway/.env`, `ANTHROPIC_API_KEY` is unset, and local Ollama is unreachable, so the four live golden cases cannot run. The plan's "4 failed" live result also predates the final dimension-accounting test. Until a live run passes, there is no end-to-end proof, and the plan says that must come before any Graphiti work.

## Next steps

1. Create `gateway/.env` with a real key, or start Ollama.
2. Rerun the live golden cases and review the output.
3. Fix the stale "Fixes" paragraph and the mypy count in the plan.
4. Commit only gateway files, one task per commit.
