# Decisions

- 2026-10-19 — Embeddings stay unlabelled (no `search_document:`/`search_query:`). Why: existing vectors came through gateways that drop the flag, and adding labels now would stop new vectors matching old ones; revisit only with a full re-embed.
- 2026-10-19 — Golden set has no image-transcription case. Why: no real image with known words yet; add one when there is.
- 2026-10-19 — `.env` is loaded when the app is created, and shell variables win over it. Why: `AI_OS_TOKEN` is read at import time, and an explicit shell export should beat a file.
- 2026-10-19 — any-llm 1.29.0 replaces the hand-written Claude/GPT/Ollama adapters, behind `llm/providers/llm.py`. Why: borrow plumbing; 1.29.0 was the newest release over three weeks old.
- 2026-10-19 — Retries stay in the provider-call stage (tenacity); vendor SDK retries are off. Why: one place decides retries, and the reply's `retries` count stays true.
- 2026-10-19 — Claude `input_tokens` now include cache reads and writes, as OpenAI's do. Why: pricing subtracts cache tokens from input, so the old Claude numbers under-billed cached calls.
- 2026-10-19 — Kept the prompted tool-calling fallback for local models. Why: phi4 and gemma4 are not on the native-tool list and Ollama was not running to check; any-llm has no fallback.
- 2026-10-19 — Removed the in-process trace store and `/api/observability/traces/*`, `/refusals`; all OpenTelemetry code is in `gateway/telemetry.py`. Why: it duplicated OpenTelemetry; a real trace viewer comes later, and until then spans go nowhere.
