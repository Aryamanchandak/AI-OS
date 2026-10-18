# Step 2b: Remove Streaming and the Semantic Cache

## Why
- **Streaming** (sending a reply word by word as it's written) is a second route through the pipeline. Nothing needs it yet.
- **The semantic cache** answers new questions with saved answers to similar ones. It's off by default. For financial data it risks returning the wrong figure, such as Q2 revenue when you asked for Q3.

Together they're about 550 lines.

## Definition of done
- `/chat` with `stream: true` is rejected with a clear error message. It no longer returns a streamed reply.
- The `/cache/*` routes, `config/cache.yaml` and the cache database setting are gone.
- The full test suite passes, and you've seen the output.

## Decisions already made
- Streaming isn't needed yet (your answer: "No").
- Remove the semantic cache (your answer: "yes get rid of it").
- **Keep Claude's prompt caching.** That's where Anthropic stores your long instructions and charges less to reuse them. It's a different feature: the `cache_control` marker handled in `src/gateway/llm/providers/content.py` (`flatten_system`). It stays.

## Open questions
- None.

## Tests first
- `POST /api/llm/chat` with `"stream": true` returns a 422 error ("invalid request") that says streaming isn't supported.
- `GET /api/llm/cache/stats` and `POST /api/llm/cache/purge` return 404 ("not found").
- Startup no longer creates `semantic_cache.sqlite`. Assert this in the existing startup test in `tests/test_platform_security_control.py`.

## Files changed

| File | Change |
|---|---|
| `src/gateway/llm/cache/` (`__init__.py`, `README.md`) | **Delete the folder** (~320 lines) |
| `src/gateway/llm/orchestration/cache_lookup.py`, `cache_store.py` | **Delete** |
| `src/gateway/llm/orchestration/streaming.py` | **Delete** |
| `src/gateway/llm/orchestration/pipeline.py` | Remove the cache stages, `run_stream` and `_stream_frames` |
| `src/gateway/llm/orchestration/README.md` | Remove the cache and streaming stages from the stage list |
| `src/gateway/llm/service.py` | Remove `build_semantic_cache`, `attach_semantic_cache`, `_cache_embed` and `stream_chat` |
| `src/gateway/llm/models.py` | Remove the `semantic_cache` field. Reject `stream: true` with a clear message. |
| `src/gateway/llm/api/routes.py` | Remove the `/cache/stats` and `/cache/purge` routes and the streaming branch in `/chat` |
| `src/gateway/llm/api/preflight.py` | Drop the `semantic_cache=False` argument |
| `src/gateway/llm/providers/base.py` and each provider's `stream()` (`anthropic`, `openai`, `openai_compatible`, `ollama`) | Remove `stream()` |
| `src/gateway/app/lifespan.py` | Stop building the cache and checking its health |
| `src/gateway/platform/configuration/glc.py` | Remove `cache_db` |
| `config/cache.yaml` | **Delete the file** |
| READMEs mentioning streaming or the cache: `src/gateway/README.md`, `llm/README.md`, `llm/api/README.md`, `llm/providers/README.md`, `llm/providers/openai/README.md`, `llm/providers/openai_compatible/README.md`, `platform/observability/README.md` | Remove the streaming and cache wording. Update every mention, per your Mistakes log. |
| `tests/test_llm.py`, `tests/test_llm_orchestration.py`, `tests/test_restored_contracts.py`, `tests/test_platform_security_control.py`, `tests/test_standalone_bootstrap.py`, `tests/test_llm_contract.py` | Remove or adjust the cache and streaming parts |
| `contracts/openapi.json` | Regenerate |

## Test files to delete
- **`tests/test_llm_streaming.py`**, the whole file. It tests only streaming.
- **Test functions** in the files above that exercise only the semantic cache or streaming. They'll be listed by name at the start of the session.

## Not in this step
- Prompt caching (it stays).
- Anything about batch (step 2c).

## Verification
1. Run `.venv/bin/pytest -q` before starting, and record the result.
2. Add the new tests and confirm they fail.
3. Make the changes. Run `.venv/bin/python scripts/export_openapi.py`, then `.venv/bin/pytest -q`. All should pass; show the output.
4. Run `grep -rn "semantic_cache\|run_stream\|stream_chat\|cache_lookup\|cache_store" src tests config`. Expect no matches.

## Commit
```
git add -A .                                            # stage every change in gateway/
git commit -m "Shrink step 2b: remove streaming and semantic cache"   # save the snapshot
```
