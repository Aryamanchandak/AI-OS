# Step 6: Replace the Hand-Written Provider Code with any-llm; OpenTelemetry Behind One Adapter

## Why
About 1,000 lines in `llm/providers/` are plumbing written by hand: web requests to each provider, translating between their formats, guessing what each model can do, and cleaning up response schemas. Your rule is "borrow plumbing, build judgment". Mozilla's **any-llm** (`any-llm-sdk`) does this job, using each provider's official library underneath.

The gateway also keeps its own in-memory copy of recent traces (timelines of each request), when OpenTelemetry already records them. And retries are written by hand, which breaks your rule "never write retry code yourself".

**Ladder step:** "replace", the last rung, for the provider code.

## Definition of done
- Every provider call goes through **one file**, `src/gateway/llm.py`, which wraps any-llm. That file is under 200 lines, and nothing else imports `any_llm`.
- The golden set from step 5 passes, unchanged, which proves the swap changed nothing you can see.
- Retries come from a library: any-llm's built-in retries, or `tenacity`. No hand-written retry loop remains.
- Every OpenTelemetry import lives in **one file**, `src/gateway/telemetry.py`. The in-memory trace store and its routes are gone.
- The limit on simultaneous calls is set in config, not hard-coded as 32.
- The full test suite passes, and you've seen the output.

## Decisions already made
- Use any-llm, tenacity (only if needed) and OpenTelemetry. All approved.
- Keep your own `pricing.py` and budget code. The any-llm library doesn't do pricing; that's in Mozilla's separate Otari gateway, which hasn't been evaluated.
- Add a trace viewer such as Arize Phoenix later, the first time you need to debug. Until then, if no export target is set, traces go nowhere and cost nothing.

## Open questions (answer before the step starts)
1. **Version to pin.** The newest release was 1.37.0 (2026-10-16). Pick a release that has been out for at least a few weeks on the day this step starts, and confirm it.
2. **Claude prompt caching.** Check whether any-llm passes Anthropic's `cache_control` markers through. If it doesn't, cached system prompts stop being discounted, and costs go up. Escalate in order: configure → any-llm's official extension points → handle it in `llm.py` → raise an upstream issue. **Stop and tell you which rung we're on.**
3. **Ollama embeddings and the local tool workaround.** Check that any-llm covers Ollama chat and embeddings for your models (`phi4`, `gemma4`, `nomic-embed-text`). Check whether the Ollama tool-calling workaround (`ollama/tools.py`) is still needed.
4. **New files and dependencies.** Please OK `src/gateway/llm.py`, `src/gateway/telemetry.py`, and `any-llm-sdk` with the `anthropic`, `openai` and `ollama` extras. Add `tenacity` only if needed.

## Tests first
- **Golden set:** `pytest -m golden` passes before the swap. Record the output. It must pass again after the swap.
- **Adapter test:** with a fake any-llm client, `llm.py` turns one chat request into the right any-llm call: model string, messages, tools, response format and max tokens. It turns the reply back into the gateway's `ProviderResult`, with tokens and the model name.
- **Retry test:** a fake provider that fails once with a "try again later" error and then succeeds → the call succeeds, and the ledger records 1 retry.
- **Trace test:** with an in-memory OpenTelemetry exporter, one chat call produces spans for each stage. This is the OpenTelemetry library's own test exporter, not the gateway's store.
- **Concurrency test:** the cap value comes from config.

## Files changed

| File | Change |
|---|---|
| `src/gateway/llm.py` | **New.** The only any-llm caller: chat, embed, and translating errors and usage |
| `src/gateway/llm/providers/` (`anthropic/`, `openai/`, `openai_compatible/`, `ollama/`, `http.py`, `content.py`, `capabilities.py`, both `schema.py` files, `ollama/tools.py`) | **Delete.** `content.py` goes only after `content_has_image` and `flatten_system` move to where they're still needed. `ollama/tools.py` goes only if question 3 says it's not needed. |
| `src/gateway/llm/providers/base.py`, `registry.py` | Shrink to the gateway's own types (`ProviderResult`, `ProviderCapabilities`) and a registry that reads capabilities from config |
| `config/providers.yaml` (or a section of an existing file) | **New or extended:** each provider's model list and capabilities (vision, tools, structured output), stated plainly instead of guessed from model names. Ask before creating the file. |
| `src/gateway/llm/orchestration/provider_call.py` | Remove the hand-written retry loop and the hard-coded 32. Read the cap from config. |
| `src/gateway/llm/service.py`, `orchestration/pipeline.py` | Call `llm.py`. Get the tracer from `telemetry.py`. |
| `src/gateway/telemetry.py` | **New.** Holds every OpenTelemetry import: setup, the tracer, the exporter |
| `src/gateway/platform/observability/` (`capture.py`, `routes.py`, `__init__.py`, `redaction.py`, `README.md`) | **Delete** the in-memory trace and refusal store, and the `/traces/*` and `/refusals` routes. Move `safe_error` to where it's still used. |
| `src/gateway/app/main.py`, `lifespan.py`, `dependencies.py`, `router_registry.py` | Remove `DiagnosticCapture` and the observability routes. Use `telemetry.py`. |
| `src/gateway/platform/networking/` | **Delete** if nothing makes web requests any more after the swap |
| `pyproject.toml`, `uv.lock` | Add `any-llm-sdk` (pinned), and `tenacity` if needed, with `uv add`. Remove `jsonschema` if it's now unused. |
| `docs/dependencies.md` | One entry for each library added: job, version, why chosen, exit plan |
| READMEs under `src/gateway/llm/` and `src/gateway/platform/` | Update or delete them alongside their folders |
| `tests/test_llm_providers.py` | Replace with adapter tests for `llm.py` (see below) |
| `tests/test_restored_contracts.py`, `tests/test_llm_orchestration.py` | Remove the trace-store tests. Adjust the retry tests. |
| `contracts/openapi.json` | Regenerate |

## Test files to delete
- **`tests/test_llm_providers.py`**, the whole file. It tests the hand-written adapters being removed, and is replaced by `tests/test_llm_adapter.py` (new; ask first).
- **Test functions** for the in-memory trace store in `tests/test_restored_contracts.py`. They'll be listed by name at the start of the session.

## Not in this step
- Together (step 7).
- Pricing from a library (keep your own).
- A trace viewer.

## Verification
1. `.venv/bin/pytest -m golden -v` **before** any change. Save the output.
2. Run `.venv/bin/pytest -q` before starting, and record the result.
3. Add the new tests and confirm they fail.
4. Make the changes. Run `.venv/bin/pytest -q`; all should pass. Show the output.
5. `.venv/bin/pytest -m golden -v` **after**. The same cases pass. Compare costs and token counts with the "before" run, and explain any difference.
6. Run `grep -rln "any_llm" src`. Expect only `src/gateway/llm.py`.
7. Run `grep -rln "opentelemetry" src`. Expect only `src/gateway/telemetry.py`.
8. Run `wc -l src/gateway/llm.py`. Expect under 200 lines.

## Commit
```
git add -A .                                              # stage every change in gateway/
git commit -m "Shrink step 6: any-llm behind llm.py; OpenTelemetry behind telemetry.py"   # save the snapshot
```
