# Step 5: First Real Request End to End, and the Golden Set

## Why
The gateway has never handled a real request. Two things block it:
- **API keys are never loaded from `.env`.** No loader has been written.
- **There's no golden set**: a few real requests with known good outcomes that prove the gateway works and keep proving it after every change.

This step makes the gateway usable. It also gives steps 6–7 something to be checked against.

## Definition of done
- With keys in `.env`, starting the gateway and sending one real Claude chat request returns a correct answer.
- That call appears in the ledger with real token counts and a **non-zero** USD cost.
- The golden set (3–5 real requests, saved as YAML) passes when run on demand with `pytest -m golden`.
- The normal test suite still passes **without** keys or network.
- `/chat` and `/embed` replies are checked against typed response models (`ChatResponse`, `EmbedResponse`, `ToolCall`), so the contract file describes them exactly.

## Decisions already made
- Keys come from `.env` only, through `python-dotenv` behind one adapter file. They're never printed or logged.
- The golden set is plain YAML (your rule: test cases stay in Markdown/YAML/CSV).
- Golden runs cost real money, so they run only when asked: `pytest -m golden`. They never run with the normal suite.

## Open questions (answer before the step starts)
1. **New files.** Please OK these: `src/gateway/env.py` (the `.env` adapter), `.env.example` (variable names only, no values), `tests/golden/cases.yaml` and `tests/test_golden.py`.
2. **The golden cases themselves.** Your rules say they should be real requests with known good outcomes. Give me 3–5 from your actual use, or approve these starting cases:
   - Claude chat: "Reply with exactly the word OK" → the reply is `OK`; one ledger row; cost above $0.
   - Structured output through the `knowledge-extraction-v1` profile on a short real paragraph of yours → valid JSON matching the schema.
   - Embedding through the `chunker-v1` profile (Ollama `nomic-embed-text`) → 768 numbers.
   - Image transcription through `image-transcription-v1`, on one small real image of yours → contains the expected words.
   - Budget refusal: a `session:*` limit of $0 → refused, and no provider call made.
3. **A small amount of spend.** Each golden run costs a few cents. OK?

## Subsection: embedding prefix check
nomic needs each text to start with a label: `search_document:` for something stored, `search_query:` for a search. The gateway currently **throws away** the "document or query" flag (`del task_type` in `src/gateway/llm/providers/ollama/__init__.py`), so it never adds a label.

Steps:
1. **Find out who made your existing vectors**, and whether that code added `search_document:` itself. This needs a read-only look at your ingestion code in `../Ingestion 2`, with your OK at that point.
2. **Decide with you:**
   - **Old vectors have the label:** the gateway adds the labels from now on, configured per profile in `config/profiles.yaml`, not in code.
   - **Old vectors don't have the label:** adding labels now would make new vectors stop matching old ones. Choose between (a) re-embedding everything with labels, which gives better search but costs time, or (b) keeping no labels. Don't change anything until you choose.
3. Add a golden case for whichever behaviour is chosen.

## Tests first
- **`.env` test:** a temporary `.env` file with `ANTHROPIC_API_KEY=test` makes the `anthropic` provider appear. With no `.env`, startup still works, with no providers.
- **No-leak test:** the key's value never appears in log output, the `/providers` reply, or a startup error message.
- **Response-model tests:** the `/chat` and `/embed` replies validate against `ChatResponse` and `EmbedResponse`. The contract file lists their fields.
- The golden tests are skipped unless you pass `-m golden`.

## Files changed

| File | Change |
|---|---|
| `src/gateway/env.py` | **New**, about 15 lines. Loads `gateway/.env` with `python-dotenv` once, at startup. The only file that imports `dotenv`. |
| `src/gateway/app/main.py` | Call the `.env` loader before building the app |
| `.gitignore` (gateway folder) | **Add `.env`.** Today it isn't ignored, so a key could be committed. Check with `git check-ignore -v .env`. |
| `.env.example` | **New.** `ANTHROPIC_API_KEY=`, `OPENAI_API_KEY=`, `OLLAMA_URL=`, and so on, with no values |
| `src/gateway/llm/models.py` | Make `ChatResponse`, `EmbedResponse` and `ToolCall` match what the pipeline really returns |
| `src/gateway/llm/api/routes.py` | Attach `response_model=` to `/chat` and `/embed` |
| `tests/golden/cases.yaml` | **New**: the golden cases |
| `tests/test_golden.py` | **New**: reads `cases.yaml` and runs each case against the real gateway, then checks the reply and the ledger row |
| `pyproject.toml` | Register the `golden` test marker, and exclude it from default runs |
| `README.md` | "How to run": put keys in `.env`, start the gateway with `uvicorn main:app`, run `pytest -m golden` |
| `contracts/openapi.json` | Regenerate |
| (prefix subsection) `src/gateway/llm/providers/ollama/__init__.py`, `config/profiles.yaml` | Only if a labelling change is chosen |

## Test files to delete
- None.

## Not in this step
- any-llm (step 6). This step proves the current code first, so step 6 has something to compare against.
- Graphiti's OpenAI-format address (a later feature).

## Verification
1. `.venv/bin/pytest -q`: everything passes, with no keys needed.
2. `git check-ignore -v .env` names `.gitignore`, which proves the key file can't be committed.
3. **You** put real keys in `gateway/.env`. I never see or print them.
4. `.venv/bin/uvicorn main:app --port 8000` starts the gateway. Then send one Claude request with `curl` (exact command given at the time). The answer and a ledger row with a non-zero cost should come back.
5. `.venv/bin/pytest -m golden -v`: all golden cases pass. Show you the output.

## Commit
```
git status --short .          # check that .env is NOT listed. If it is, stop.
git add -A .                  # stage every change in gateway/
git commit -m "Shrink step 5: .env loader, first end-to-end request, golden set"   # save the snapshot
```
