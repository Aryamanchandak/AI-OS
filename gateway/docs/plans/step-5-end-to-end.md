# Step 5: First Real Request End to End, and the Golden Set

**Why.** The gateway has never handled a real request: keys are never loaded from `.env`, and there's no golden set to prove it works after every change.

**Done when.** With keys in `.env`, one real Claude chat returns a correct answer and lands in the ledger with real tokens and a non-zero cost. 3–5 golden cases in YAML pass with `pytest -m golden` (never in the normal run, since they cost money). The normal suite still passes with no keys or network. `/chat` and `/embed` replies validate against `ChatResponse`, `EmbedResponse` and `ToolCall`.

**Decided.** Keys come from `.env` only, through `python-dotenv` behind one adapter, never printed or logged. Golden cases are plain YAML. `.env` is already in `.gitignore`.

**Answer before starting.**
1. OK new files: `src/gateway/env.py`, `.env.example` (names only), `tests/golden/cases.yaml`, `tests/test_golden.py`.
2. The golden cases: give me real ones, or approve these: "Reply with exactly OK" → `OK`, one ledger row, cost > $0; `knowledge-extraction-v1` on a real paragraph → valid JSON; `chunker-v1` embedding → 768 numbers; `image-transcription-v1` on a real image → expected words; a `session:*` limit of $0 → refused, no provider call.
3. A few cents of spend per golden run: OK?

**Embedding prefix check.** nomic expects `search_document:` / `search_query:` labels, but the gateway throws the flag away (`del task_type` in `providers/ollama/__init__.py`). First find out whether your existing vectors were labelled (read-only look at `../Ingestion 2`, with your OK). If they were, the gateway adds labels per profile in config. If not, choose: re-embed everything with labels, or keep no labels. **Change nothing until you choose.** Add a golden case for the result.

**Tests first.** A temporary `.env` with `ANTHROPIC_API_KEY=test` makes `anthropic` appear; no `.env` still starts. The key value never appears in logs, `/providers` or startup errors. Response models validate. Golden tests skip without `-m golden`.

**Verify.** You put real keys in `gateway/.env` (I never see them). Start with `.venv/bin/uvicorn main:app --port 8000`, send one `curl` request, then `.venv/bin/pytest -m golden -v`.

Commit: `git status --short .` (stop if `.env` is listed), `git add -A .`, `git commit -m "Shrink step 5: .env loader, first end-to-end request, golden set"`.
