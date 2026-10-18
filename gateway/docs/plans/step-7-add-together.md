# Step 7: Add Together.ai

## Why
You want Together alongside Claude and GPT. After step 6, adding a provider should mean adding config, not code. This step proves that.

## Definition of done
- With `TOGETHER_API_KEY` in `.env`, a request through a Together profile returns a correct answer.
- That call is logged in the ledger with a non-zero, correct cost.
- One new golden case for Together passes, and all the earlier golden cases still pass.
- No new Python code beyond config, unless any-llm needs it. If it does, stop and tell you.

## Decisions already made
- Use Together through any-llm's built-in `together` provider: install the `together` extra.

## Open questions (answer before the step starts)
1. **What is Together for?** Which jobs, and which models? For example, a cheap open model for bulk extraction, or embeddings.
2. **Prices** for those models, taken from Together's pricing page on the day, with the page and date shown to you for confirmation.
3. **Embeddings on Together?** If yes: different models produce vectors that can't be compared with each other, so **never mix them with your nomic vectors in one collection.**

## Tests first
- With a fake Together response, a request using the Together profile goes to the `together` provider with the right model.
- The pricing test from step 2a also covers the new Together models.
- A golden case for the chosen job.

## Files changed

| File | Change |
|---|---|
| `pyproject.toml`, `uv.lock` | Add the `together` extra to `any-llm-sdk` (`uv add "any-llm-sdk[...,together]"`, pinned) |
| `config/providers.yaml` (from step 6) | Add the `together` provider with its models and capabilities |
| `config/profiles.yaml` | Add the Together profiles |
| `config/pricing.yaml` | Add the Together model prices |
| `.env.example` | Add `TOGETHER_API_KEY=` |
| `tests/golden/cases.yaml` | Add the Together case |
| `tests/test_llm_adapter.py` | Add the Together routing test |
| `docs/dependencies.md` | Note the `together` extra |

## Test files to delete
- None.

## Not in this step
- Real batching on Together (later feature).

## Verification
1. Run `.venv/bin/pytest -q` before starting, and record the result.
2. Add the new tests and confirm they fail.
3. Make the changes. Run `.venv/bin/pytest -q`; all should pass. Show the output.
4. **You** add `TOGETHER_API_KEY` to `.env`.
5. `.venv/bin/pytest -m golden -v`: every case, old and new, passes. Show the output.

## Commit
```
git add -A .                                       # stage every change in gateway/
git commit -m "Shrink step 7: add Together.ai"     # save the snapshot
```
