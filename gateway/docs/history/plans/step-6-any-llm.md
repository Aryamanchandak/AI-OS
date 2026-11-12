# Step 6: any-llm Behind `llm.py`; OpenTelemetry Behind `telemetry.py`

Outline only. Detailed when step 5 is done, since step 5 changes what this replaces.

**Why.** About 1,000 lines in `llm/providers/` are hand-written plumbing (HTTP calls, format translation, guessing model abilities). "Borrow plumbing, build judgment": Mozilla's any-llm (`any-llm-sdk`) does this job. Retries are also hand-written, and an in-memory trace store duplicates OpenTelemetry. Ladder rung: **replace**.

**Done when.** Every provider call goes through `src/gateway/llm.py` (under 200 lines; nothing else imports `any_llm`). The step 5 golden set passes unchanged, with costs and tokens compared before and after. Retries come from a library (any-llm's own, or `tenacity`). Every OpenTelemetry import is in `src/gateway/telemetry.py`; the trace store and `/traces/*`, `/refusals` are gone. The concurrency cap (32 today) comes from config.

**Decided.** any-llm, tenacity (only if needed) and OpenTelemetry are approved. Keep your own pricing and budget code. Add a trace viewer later; with no export target, traces go nowhere.

**Answer before starting.**
1. Which any-llm version to pin: one out for at least a few weeks on the day.
2. **Claude prompt caching:** does any-llm pass `cache_control` through? If not, cached prompts lose their discount. Escalate configure → official extension points → handle in `llm.py` → upstream issue, and **stop and tell you which rung we're on.**
3. Does any-llm cover Ollama chat and embeddings for `phi4`, `gemma4`, `nomic-embed-text`, and is the `ollama/tools.py` workaround still needed?
4. OK new files `llm.py`, `telemetry.py`, `tests/test_llm_adapter.py`, possibly `config/providers.yaml`, and the dependency `any-llm-sdk[anthropic,openai,ollama]`.

**Test deletions you'd be OK-ing:** all of `tests/test_llm_providers.py` (replaced by `test_llm_adapter.py`) and the trace-store test functions.
