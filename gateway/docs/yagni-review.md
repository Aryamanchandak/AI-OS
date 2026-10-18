# Gateway YAGNI Review

As of 2026-10-18 · Reviewer: Claude · Scope: every `.py` file in `gateway/src/gateway`

About 1,500–2,000 of the gateway's ~4,000 lines of Python can go. Most of it is features built before one request has worked end to end, plus code that redoes what a library already does. Nothing has been changed yet. This is a list for you to approve, tier by tier.

---

## Summary

Start with Tier 1: about 350 lines of trunk code that nothing calls. It's the lowest-risk cut and needs no decisions from you. Tiers 4–6 hold the big savings, but each one needs an answer from you first.

| Tier                                                                                                                                                                     | What it is                             | Lines saved (approx.) | Risk                              | Tests that go with it                                                                      | Needs your answer? |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- | --------------------- | --------------------------------- | ------------------------------------------------------------------------------------------ | ------------------ |
| 1 [WE CAN SAFELY GET RID OF THIS]                                                                                                                                        | Dead code nothing calls                | ~350                  | Low                               | `test_platform_security_control.py` (ledger part), `test_foundation.py` (settings part)    | No                 |
| 2 [WHY DO WE HAVE THIS IN THE FIRST PLACE ?]                                                                                                                             | Routes returning fake or empty data    | ~30                   | Low, but changes the API contract | `contracts/openapi.json` regenerated                                                       | No                 |
| 3 [ NEED TO LOOK INTO CANT DELETE WILLY NILLY]                                                                                                                           | Same job done in several places        | ~100                  | Low–medium                        | Few; mostly refactor                                                                       | No                 |
| 4 [WE NEED TESTS RIGHT ? I MEAN ATLEAST WHILE WE DONT SIGN OFF ON THE CODE, BUT EVEN THEN IT ALLOWS YOU TO KEEP A CHECK ON THE THINGS YOU HAVE MADE, SO THEY DONT BREAK] | Non-LLM features inside the gateway    | ~100–300              | Medium (outside callers?)         | `test_restored_contracts.py`, `test_llm_contract.py`, `test_foundation.py`, `test_main.py` | Yes                |
| 5 [ WHAT DOES THIS MEAN ? I MEAN OLD TESTS OR TESTS TESTING THINGS THAT WE DONT REALLY HAVE ANYMORE SURE BUT THE CODE NEEDS TO WORK END TO END TO BE USABLE]             | Features built before end-to-end works | ~600                  | Medium                            | `test_llm.py`, `test_llm_streaming.py` and others                                          | Yes                |
| 6 [THIS IS INTERESTING, WHAT DO YOU PROPOSE HERE ?]                                                                                                                      | Hand-written versions of library jobs  | ~1,400                | High (replacement)                | Most of `test_llm_providers.py`                                                            | Yes                |

The line counts are estimates from reading the code, not measured diffs. Removing a feature means removing its tests too, and your rules need your explicit OK for each test file.

---

## What was reviewed

I read every `.py` file under `gateway/src/gateway` in full, about 4,000 lines of Python. I checked what uses each piece by searching `src`, `tests`, `scripts`, `contracts`, `docs` and `config`. I searched nothing outside the gateway folder, so whether outside callers use a route is a question for you.

| Component                          | Folder                            | Lines (approx.) | One-line job                                                                                      |
| ---------------------------------- | --------------------------------- | --------------- | ------------------------------------------------------------------------------------------------- |
| LLM providers                      | `llm/providers/`                  | ~1,500          | Hand-written HTTP adapters for OpenAI, Anthropic, Gemini, Ollama and 5 OpenAI-compatible services |
| LLM pipeline                       | `llm/orchestration/`              | ~430            | Ten stages a chat request passes through                                                          |
| Semantic cache                     | `llm/cache/`                      | ~320            | Answers repeat questions from stored responses                                                    |
| Cost and budgets                   | `llm/economics/`                  | ~290            | Pricing, spend tracking, budget limits                                                            |
| LLM models and service             | `llm/models.py`, `llm/service.py` | ~390            | Request shapes and the facade the routes call                                                     |
| LLM routes                         | `llm/api/`                        | ~240            | HTTP endpoints for chat, embed, budget, cost, cache                                               |
| Platform [WHAT DOES THIS DO ?]S    | `platform/`                       | ~700            | Config, service registry, database helper, tracing, HTTP client                                   |
| App wiring [WHY DO WE NEED THIS ?] | `app/`                            | ~320            | Builds the FastAPI app, auth, startup                                                             |
| Security                           | `security/ssrf.py`                | ~145            | Safe downloading of image URLs                                                                    |
| Audit                              | `audit/`                          | ~90             | Append-only log of calls                                                                          |
| Ledger                             | `ledger/`                         | ~115            | A second call log (unused)                                                                        |

The `llm/` folder alone is about 3,200 lines.

---

## CLAUDE.md rules already broken

Five of your own rules are broken today. Each one is a reason to cut, not just tidy.

| Rule                                                                                                          | Where it's broken                                                                                                                 | Why it matters                                         |
| ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| ~1,500 lines per component, then stop and reassess                                                            | `llm/` is ~3,200 lines                                                                                                            | It's your own trigger for a rethink                    |
| One thin adapter file per library [OPENTELEMETRY IS FOR WHAT ?]                                               | `yaml` is imported in ~9 files; `httpx` and `opentelemetry` in many more                                                          | Swapping or upgrading a library touches everything     |
| Never write retry code yourself                                                                               | Hand-written retry loop in `llm/orchestration/provider_call.py`                                                                   | Retry is plumbing; a library does it better            |
| Never parallelise without a measured bottleneck [YEAH TRUE, GOOD TO HAVE IT THO, NOT SURE BAUT HAVING 32 THO] | `/chat/batch` runs calls in parallel; a 32-slot limit (semaphore, i.e. a cap on how many calls run at once) in `provider_call.py` | Added before anything was measured                     |
| Flag new features before one request works end to end                                                         | Semantic cache, five-dimension budgets, vision, batch, Gemini context cache                                                       | Your notes say the gateway has never worked end to end |

There's one more risk, though it doesn't break a rule. `security/ssrf.py` uses private internals of httpx, the HTTP library (`httpcore._backends`, `httpx._config`, `transport._pool`). "Private" means undocumented, so any upgrade can break it without warning.

---

## Tier 1 — Dead code, safe to delete

No production code calls anything below, so deleting it changes no behaviour. Together it's about 350 lines.

| Item                                                                                                                                                                                                                                      | File                                                                                   | Lines (approx.) | What it is and why it's dead                                                                                                                                                                                               | Tests affected                                     |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `CallLedger` (whole `ledger/` package)[WHAT WAS IT MADE FOR THEN ? AND WHAT CAN IT BE IF IT WASNT SO UNDER UTILISED ?]                                                                                                                   | `ledger/repository.py`, `ledger/__init__.py`, `app/lifespan.py`, `app/dependencies.py` | ~115            | A second call log. It's built at startup and health-checked, but nothing writes to it except one test. It also lists its 28 columns twice. **Keep the database path:** the budget code stores its tables in the same file. | Ledger test in `test_platform_security_control.py` |
| `GatewaySettings` + `gateway.yaml`                                                                                                                                                                                                        | `platform/configuration/settings.py`, `app/lifespan.py`                                | ~45             | Loaded, never read. The real host and port come from `services.yaml`.                                                                                                                                                      | Settings tests in `test_foundation.py`             |
| Response models `ChatResponse`, `EmbedResponse`, `RouterDecision`, `ToolCall [WELL THIS ISNT GOOD IS IT, THIS SHOULD BE USED ?]`                                                                                                          | `llm/models.py`                                                                        | ~90             | Defined, but no route uses them. Routes return plain dicts.                                                                                                                                                                | None                                               |
| `AuditStore.query`, `failure_policy [WHY ?]`                                                                                                                                                                                              | `audit/store.py`                                                                       | ~20             | Never called.                                                                                                                                                                                                              | None                                               |
| `assert_safe_url [WHY?]`                                                                                                                                                                                                                  | `security/ssrf.py`                                                                     | ~4              | Never called.                                                                                                                                                                                                              | None                                               |
| `GLCPaths.load_mapping [WHAT DOES THIS DO.? ]`                                                                                                                                                                                            | `platform/configuration/glc.py`                                                        | ~10             | Never called.                                                                                                                                                                                                              | None                                               |
| `content_has_image [NOT SURE AGAIN WHAT THIS DOES ?ALSO INBOUND IS NOT THE PERVUEW OF THIS GATEWAY ONLY OUTBOUND LLM CALLS AND INBOUND LLM CALLS, WHY ARE WE LOOKING AT IMAGES HERE, UNLESS THE IMAGES ARE BEING SENT FOR TRANSCRIPTION]` | `llm/providers/content.py`                                                             | ~5              | Never called.                                                                                                                                                                                                              | None                                               |
| `Usage`                                                                                                                                                                                                                                   | `llm/economics/meter.py`                                                               | ~5              | A copy of `ProviderUsage` that nothing uses.                                                                                                                                                                               | None                                               |
| `thinks_by_default` and the branches its own comment calls "dead in practice"                                                                                                                                                             | `llm/providers/capabilities.py`                                                        | ~25             | Kept only to match the old code exactly.                                                                                                                                                                                   | Possibly `test_llm_providers.py`                   |
| Budget `projection`, `alerts`, `load_overrides`                                                                                                                                                                                           | `llm/economics/budget.py`                                                              | ~5              | Read from config, only echoed back.                                                                                                                                                                                        | None                                               |
| `max_retries`, `max_concurrency` arguments                                                                                                                                                                                                | `llm/orchestration/provider_call.py`                                                   | ~2              | Never set by anything.                                                                                                                                                                                                     | None                                               |
| Stale docstring about "Plans 02, 04–06"                                                                                                                                                                                                   | `app/dependencies.py`                                                                  | ~4              | Refers to plans that no longer apply.                                                                                                                                                                                      | None                                               |

Don't remove `python-dotenv`. It looks unused because the `.env` loader hasn't been written yet, but you'll need it. [THE ISSUE WITH THE ABOVE LIST IS THAT WHILE ITS USEFUL TO REDUCE THE NUMBER OF LINES, IT IS ALSO NOT GREAT BECAUSE THEY ARE USEFUL, FEATURES I THINK TO HAVE SO THE QUESTION IS WHY ARENT THEY BEING USED, OUT OF THESE WHICH FEATURES ARE TRULY NOT REQUIRED] 

---

## Tier 2 — Routes that return fake data

These routes answer, but with made-up or empty values. A caller that trusts them would be misled, so removing or fixing them is safer than keeping them.

| Route or function | File | What's fake |
| --- | --- | --- |
| `GET /routers` | `llm/api/routes.py` | Returns every field empty. Routing doesn't exist. |
| `GET /telemetry` | `llm/api/routes.py` | Returns a hard-coded answer. |
| `GET /embedders` | `llm/api/routes.py` | `fixed_dim: 768`, `max_input_chars` and `backoff_steps_s` are constants, not real values. |
| `status()` | `llm/service.py` | Always reports every provider as available. |
| `providers()` | `llm/service.py` | `shortcuts` and `limits` are always empty. |

All of these are recorded in `contracts/openapi.json`, the saved description of every route. A test fails if that file is out of date, so any change here means running `python scripts/export_openapi.py` afterwards. [WHY IS THIS ?] 

---

## Tier 3 — Duplication

The same job is done in several places. Merging each one into a single place saves about 100 lines and makes every trunk module easier to explain in one line.

| Duplicated job | Where | Suggested single home |
| --- | --- | --- |
| Recording each LLM call | In-memory `Meter` (`llm/economics/meter.py`), the audit database (`audit/store.py`), and the unused ledger | The audit database. The in-memory copy is lost on restart, yet `/calls` and `/cost/*` read from it. |
| "Load a YAML file, check it's a mapping, raise a clear error" | ~6 copies: settings, service registry, profiles, pricing, budgets, provider registry, plus `service.py` | One `config.py` adapter. This also fixes the one-adapter-per-library rule for `yaml`. |
| `validate_host` | `platform/configuration/settings.py` and `platform/service_registry/registry.py` (identical) | Disappears if Tier 1 removes settings |
| Opening SQLite | The shared `SQLiteDatabase` helper vs. a separate `_connect` in `llm/economics/budget.py` | The shared helper |
| Ledger column list | `CREATE TABLE` and `_migrate_columns` in `ledger/repository.py` | Disappears with Tier 1 |

---

## Tier 4 — Non-LLM features inside the gateway

Your notes say the gateway is LLM-only and other features are separate systems. The features below do other jobs. Whether they're safe to remove depends on outside callers, which I couldn't check from inside the gateway folder.

| Feature | File | Lines (approx.) | What it does | Tests affected | Question |
| --- | --- | --- | --- | --- | --- |
| Every route registered twice, under `/v1` and `/api/...` | `llm/api/routes.py`, `platform/observability/routes.py`, `app/main.py` | ~30 + test map | Keeps old URLs working. Includes two "unknown route" catch-alls. | `/v1` map in `test_llm_contract.py`, `test_restored_contracts.py` | Does anything still call `/v1`? `services.yaml` still lists `glc_legacy` on port 8111 "for callers that still use the old port." |
| Serving the shell's web files | `app/main.py` (`SHELL_DIST`, catch-all route, `/assets` mount) | ~15 | Hosts a UI | `test_main.py` (likely) | Should the shell host itself? |
| `agent_trace` proxy | `platform/observability/routes.py` | ~50 | Forwards trace requests to the agent runtime on port 8113 | `test_restored_contracts.py` | Is the agent runtime a leaf? If so, the trunk shouldn't call it. |
| Service registry | `platform/service_registry/` | ~175 | Validated host/port list for 3 services, with environment overrides | `test_foundation.py`, `test_standalone_bootstrap.py` | If the two items above go, only the gateway's own address is left, which could be one config value. |
| `/api/diagnostics/services`, `/healthz`, `/dashboard` | `app/main.py` | ~20 | Lists services; old health check; redirects to `/observability` | `test_foundation.py`, `test_main.py`, `test_restored_contracts.py` | Does anything call these? |

Keep `/health`. It's the gateway's own health check and costs four lines.

---

## Tier 5 — Features built before one request works end to end

Your CLAUDE.md asks me to flag any feature added before one request works end to end through the trunk. Each of these adds code to maintain and test before the basic path is proven.

| Feature                                                                               | File(s)                                                                                                                                                  | Lines (approx.)         | What it does                                                                                                                                                              | Tests affected                                              | Question                                                                                                                                                                 |
| ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Semantic cache                                                                        | `llm/cache/`, `orchestration/cache_lookup.py`, `orchestration/cache_store.py`, `/cache/*` routes, `config/cache.yaml`, `LLMService.build_semantic_cache` | ~400                    | Answers a new question from a stored answer to a similar one. It's off by default (`default_on: false`) and needs an embedding call on every lookup.                      | `test_llm.py`, `test_llm_streaming.py` (cache parts)        | Have you ever turned it on?                                                                                                                                              |
| Five-dimension budgets                                                                | `llm/economics/budget.py`, `meter.py`, `models.py`, budget routes                                                                                        | ~100 of ~290            | Budget limits by tenant, project, user, agent and session, plus routes to create and delete limits at runtime                                                             | Budget tests in `test_llm.py` / `test_llm_orchestration.py` | For one person, isn't agent + session enough? Tenant and project are multi-customer ideas.                                                                               |
| `/chat/batch`                                                                         | `llm/api/routes.py`, `BatchChatRequest` in `models.py`                                                                                                   | ~15                     | Runs many chat calls in parallel                                                                                                                                          | `/v1/chat/batch` entry in `test_llm_contract.py`            | Breaks the no-parallelism rule. Remove?                                                                                                                                  |
| `/vision`                                                                             | `llm/api/routes.py`, `VisionRequest` in `models.py`                                                                                                      | ~35                     | A thin wrapper that turns one image + prompt into a normal `/chat` call                                                                                                   | `/v1/vision` entry in `test_llm_contract.py`                | Callers can send the image to `/chat` directly. Remove? [NO WE NEED TO PROCESS IMAGES]                                                                                   |
| Unused request fields `auto_route`, `cost_quality_tradeoff`, `escalate`               | `llm/models.py`, `orchestration/validation.py`                                                                                                           | ~45 (mostly comments)   | The pipeline ignores them; they're left over from a routing design that isn't built. `batch` is half-used (pricing only).                                                 | None, but `contracts/openapi.json` changes                  | Remove? [I DONT KNOW WHAT THIS DOES BUT IT DOES REMIND ME THAT WE SHOULD, BUILD A BATCHING SECTION IN THIS CODE, SO WE CAN SEND AND STORE BATCHES AND RECEIVE THEM BACK] |
| Gemini context cache                                                                  | `llm/providers/gemini/context_cache.py` + use in `gemini/__init__.py`                                                                                    | ~90                     | Stores long system prompts on Google's side to cut cost                                                                                                                   | Gemini tests in `test_llm_providers.py`                     | Do you send system prompts over 1,000 characters to Gemini today?[YES, BUT WE WONT BE USING GEMINI AT ALL ANYMORE, ONLY CLAUDE OR GPT]                                  |
| Up to 10 Gemini keys                                                                  | `llm/providers/registry.py`                                                                                                                              | ~5                      | Registers `gemini_1` … `gemini_10` as separate providers                                                                                                                  | None                                                        | Do you use more than one key?[NO]                                                                                                                                       |
| Five free-tier OpenAI-compatible providers + three tiers each of OpenAI and Anthropic | `llm/providers/registry.py`, `capabilities.py`                                                                                                           | ~20 config + hint lists | Groq, Cerebras, NVIDIA, OpenRouter, GitHub; `openai-cheap/mini/pro`; `anthropic-haiku/sonnet/opus`                                                                        | Provider tests                                              | Which ones do you actually use?[JUST CLAUDE AND GPT FOR NOW, AND TOGETHER.AI]                                                                                           |
| Streaming path                                                                        | `orchestration/pipeline.py` (`run_stream`, `_stream_frames`), `orchestration/streaming.py`, `stream()` on every provider                                 | ~150                    | A second route through the pipeline for streaming replies. Only the OpenAI-compatible family streams for real; every other provider sends the whole reply at once anyway. | `test_llm_streaming.py`                                     | Does anything need streaming yet? [NO]                                                                                                                                   |
| Preflight probe                                                                       | `llm/api/preflight.py`, `/preflight` route, 3 models                                                                                                     | ~75                     | Sends a test chat and embed call to check providers work                                                                                                                  | Preflight tests                                             | Useful for golden-set checks; probably keep.                                                                                                                             |

---

## Tier 6 — Code that redoes what a library does

Your rule is "borrow plumbing, build judgment." These are plumbing written by hand. They're the biggest savings and the biggest changes, so I'd do them only after Tiers 1–5.

| Hand-written job                                                                           | File(s)                                                                                                                                         | Lines (approx.) | Library that does it                                                                                                                                             | Escalation step                       | Notes                                                                                                                                             |
| ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- | --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Retry with backoff                                                                         | `llm/orchestration/provider_call.py`                                                                                                            | ~15             | `tenacity`, or the LLM library below                                                                                                                             | Configure → replace                   | Directly breaks "never write retry code yourself."                                                                                                |
| In-memory trace and refusal storage                                                        | `platform/observability/capture.py`, `platform/observability/routes.py`, parts of `platform/observability/__init__.py`                          | ~230            | A trace viewer that reads OpenTelemetry data (Jaeger, Arize Phoenix, Langfuse)                                                                                   | Replace                               | You already export OpenTelemetry. A viewer shows traces, so the gateway doesn't have to keep its own in-memory copy.                              |
| Five provider adapters + capability guesses + schema cleaners + the Ollama tool workaround | `llm/providers/` (openai, anthropic, gemini, ollama, openai_compatible, capabilities, content, http, both `schema.py` files, `ollama/tools.py`) | ~1,000          | An LLM-routing library behind one `llm.py` adapter (e.g. LiteLLM). It also does cost tracking and fallbacks. [ I THINK LETS LOOK AT THE MOZILLA ONE NOT LITELLM] | Replace                               | This is a big decision, not a quick fix. It's the "replace" step on your ladder. It needs its own plan, DEPENDENCIES.md entry and golden-set run. |
| SSRF guard (safe image downloading)                                                        | `security/ssrf.py`, its use in `orchestration/normalization.py`                                                                                 | ~145            | None needed if callers send images as `data:` URLs (the image embedded in the request)                                                                           | Remove the need                       | SSRF means tricking a server into fetching internal addresses. The guard relies on private httpx internals.                                       |
| Pricing table                                                                              | `llm/economics/pricing.py`, `config/pricing.yaml`                                                                                               | ~70             | The LLM library above ships model prices                                                                                                                         | Replace (only with the provider swap) | Keep until the provider decision is made.                                                                                                         |

---

## Smaller structural notes

- **The pipeline is spread over 10 small files.** Stages are 13–40 lines each (`routing.py`, `profile_resolution.py`, `validation.py`, `cache_lookup.py`, `cache_store.py`, `budget.py`). Merging the tiny ones cuts file count, not lines. It's low priority, and Tier 5 already removes two of them.
- **There are 16 README files inside** `src/`**.** They aren't code, but several describe routes and features listed above. Update or remove them alongside each tier, per your mistakes-log rule about updating every old path in a doc.
- `src/ai_os_gateway.egg-info/` **is a build artifact** (a folder Python's packaging tools generate). Check that it's ignored by Git with `git check-ignore -v src/ai_os_gateway.egg-info`.

---

## Questions for you

1. Does anything outside the gateway still call `/v1/...`, `/healthz`, `/dashboard` or `/api/diagnostics/services`? Does anything still use port 8111?
2. Is the agent runtime (port 8113) a leaf? Should the shell serve its own files?
3. Have you ever turned on the semantic cache?
4. For budgets, are agent + session enough, or do you need tenant, project and user too?
5. Does anything need streaming yet?
6. Can callers send images as `data:` URLs, so the SSRF guard can go?
7. Which providers and models do you actually use?
8. Which test files may I delete along with each feature? Your rules require an explicit yes per file.

---

## Proposed order and how each step would run

One tier per session, small diffs, following your CLAUDE.md workflow:

1. **Tier 1 — dead code.** Needs no answers. Trunk change, so: plan naming every file → you OK it → delete → run the full test suite and show output → regenerate `contracts/openapi.json` if anything changed → you commit.
2. **Tier 2 — fake routes.** Same steps. The contract file is regenerated.
3. **Tier 3 — duplication.** The `config.py` YAML adapter first (it needs a new file, so I'll ask), then one call log.
4. **Tier 4 — non-LLM features.** Only after answers to questions 1–2.
5. **Tier 5 — premature features.** One feature per session, after answers to questions 3–7.
6. **Get one request working end to end and build the golden set.** Do this before Tier 6, so the replacement has something to be checked against.
7. **Tier 6 — library replacements.** Each gets its own plan and DEPENDENCIES.md entry.

Git commands after each step (run from the `gateway` folder):

```
git status                # see which files changed
git add -A                # stage all changes (new, edited, deleted files)
git commit -m "YAGNI tier 1: remove dead code"   # save a snapshot with a message
```
