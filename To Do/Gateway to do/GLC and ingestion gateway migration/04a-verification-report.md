# Plan 04a — Verification Report

**Verified:** 2026-09-21 · **Verdict: DOES NOT PASS the §9 exit gate.**

The architecture is right and should be kept. The gap is **depth and
verification**, not design. 1,720 lines were authored under
`gateway/src/gateway/llm/` against ~3,900 lines of read-only source
(`providers.py` 1,431 + `direct_providers.py` 450 + `routes/chat.py` 1,494 +
economics). The missing ~55% is where the blockers live.

`uv run pytest tests/` → **31 passed**. That number is not evidence of
equivalence; see §4.

---

## 1. What is genuinely done — keep this work

| Item | Evidence |
| --- | --- |
| Ten-stage pipeline split | `orchestration/` has all 10 stages as separate typed classes; `pipeline.py:66` |
| Route handler is thin | `api/routes.py` handlers are 1–6 lines each; no budget/routing/retry logic inline |
| **Stage 9 is unconditional** | `pipeline.py` runs `finalization` from a `finally:` block; survives retry, failover and exception paths |
| **Budget check-and-reserve is atomic** (WP E #1) | `economics/budget.py` `admit()` uses `BEGIN IMMEDIATE` + a `llm_budget_entries` reservation row, reconciled in stage 9. This is a real fix for the live money-losing bug |
| **Cache embedding reused** (WP E #4) | `CacheLookup.embedding` is carried on the context and handed to `CacheStoreStage`; one embed per miss |
| **Lifespan HTTP client reused** (WP E #3) | `lifespan.py:61` passes the single `OutboundHTTPClient().client` into every provider; closed via `DependencyContainer.close()` → `http.close()` |
| SQLite mostly off the event loop (WP E #2) | `asyncio.to_thread` wraps `budget.admit`, `budget.reconcile`, `audit.append`, `status_for`, `set_limit`, `clear_limit` |
| **HTTP isolation holds** (decision #2) | `grep LLMService\|get_llm_service` outside `llm/` returns only `app/dependencies.py` + `app/lifespan.py` container wiring. No domain leak |
| Container wiring per spec | `DependencyContainer.llm` field + `get_llm_service` accessor, constructed in `lifespan.py` |
| **`glc_v5/` untouched** | `git -C glc_v5 status --porcelain` is empty; submodule pointer unchanged; `glc/client.py` present |
| Config carried across | `profiles.yaml` byte-identical to `glc_v5/glc/profiles.yaml`; `routing.yaml` and `pricing.yaml` `diff`-identical |
| **`routing.yaml` present and unwired** | Zero references to `routing.yaml` anywhere in `gateway/src/`; `llm/routing/__init__.py` is a docstring only |
| Route surface complete | All 12 mapped routes **plus** the 7 other LLM-domain routes (`/calls`, `/routers`, `/telemetry`, `/cache/purge`, `/cost/by_agent`, `/budget/{principal}`, `/chat/profiles/{profile}`) exist at `/api/llm/*` |
| `/v1/*` alias correct | `alias_registration()` re-registers **the same `router` object** at `/v1`, `deprecated=True` — one implementation, findable by Plan 07 |

---

## 2. Blockers

### B1 — Streaming does not exist. `provider.stream()` is dead code.

```
$ grep -rn '\.stream(' gateway/src/gateway/llm/ | grep -v 'def stream'
(no matches)
```

Nothing ever calls it. All five provider `stream()` methods
(`openai_compatible`, `anthropic`, `gemini`, `ollama`, and `openai` by
inheritance) are unreachable, and each is a stub anyway — they `await
self.chat(...)` to completion and yield the whole text as one frame.

The actual `stream=true` path is `api/routes.py:26-32`: it calls the fully
buffered `service.chat()`, then fabricates at most **two** SSE frames.

Against `glc_v5/glc/routes/chat.py:826-933`, which streams incrementally:

| Legacy frame | Migrated |
| --- | --- |
| N × `{"provider":…,"delta":<token chunk>}` | **1** frame containing the entire text |
| `{"provider":…,"tool_call_delta":…}` | **absent** — no tool-call streaming |
| `{"error":…}` mid-stream | **absent** |
| `done` frame with `profile_pin_unverified` | flag **absent** |
| Per-token flush → cancellation / disconnect / backpressure work | request completes fully before the first byte; none of these work |

Hard rule #2 (*"SSE frame bytes stay byte-identical"*) is violated. Stage-9
metering does still run, so the audit invariant holds — but the streaming
contract does not.

### B2 — The JSON and error-envelope contract is unverified, and cannot be verified from this tree.

I ran the pairwise comparison §7 asks for. All 12 mapped pairs plus the 7
extra LLM routes report shape-identical. **Do not read that as a pass.**

None of the legacy LLM routes declare a `response_model`, so FastAPI emits
`"schema": {}` for every 200 response on both sides. What the comparison
actually proves is: *path and method exist, and request bodies are identical*
— the latter because `models.py` was copied verbatim. It is blind to response
bodies and error envelopes, which is exactly what hard rule #2 turns on.

The fixtures that would close this do not exist. `migration/` contains only
`baseline/contracts/{glc,gateway}-openapi.json` — no SSE fixtures, no
recorded response bodies. **Plan 01 owes this**, and until it lands the exit
gate item *"Every preserved JSON and streaming contract passes at its new
path"* is unverifiable rather than failed.

### B3 — Provider migration is incomplete; OpenAI in particular inverts decision #1.

Decision #1 put OpenAI first *specifically because* its logic is split across
both `providers.py` and `direct_providers.py` — the messiest case, to prove
the pattern. Delivered:

```python
# providers/openai/__init__.py — the entire file
class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, name, api_key, model, client):
        super().__init__(name, api_key, model, "https://api.openai.com/v1", client, vision=True)
```

10 lines. `direct_providers.OpenAIProvider` (lines 106–274, Responses API,
its own message translation, its own tool dialect) has no counterpart.

Source capability with no migrated counterpart:

| Missing | Source | Consequence |
| --- | --- | --- |
| `_gemini_inline_refs` / `_gemini_clean_schema` | `providers.py:958-1010` | Gemini structured output **breaks** on any schema with `$ref`/`$defs` — i.e. most Pydantic-generated schemas |
| `_gemini_supports_thinking` / `_gemini_thinking_knob` | `providers.py:934-957` | Gemini sets `reasoning_applied=True` but sends **no** thinking parameter — the flag lies |
| `_prompted_tool_system` / `_parse_prompted_tool_call` / `_ollama_native_tools` | `providers.py:1039,1215-1252` | Ollama models without native tool support lose tool calling entirely |
| Anthropic `cache_control` / `_flatten_system` cache blocks | `providers.py:151-173` | prompt caching gone; `cache_creation_input_tokens` is always 0 — a real cost regression |
| `anthropic_clean_schema` | `direct_providers.py:58-85` | Anthropic structured output ships unsanitized schemas |
| `model_capabilities()` per-model overrides | `providers.py:1253-1282` | `/api/llm/capabilities` reports static per-provider values, not per-model |
| Gemini context `cache_store`; `ToolCall.provider_meta` (thoughtSignature echo) | `providers.py:711`; `models.py:23` | multi-turn Gemini tool use degrades |

No per-provider checklist was produced, which §5 explicitly required *because*
the source files don't shrink as evidence.

---

## 3. Behavioral regressions (below blocker, above noise)

1. **Four request fields are accepted and silently ignored.** `models.py` was
   copied verbatim, so `cache_system`, `auto_route`, `cost_quality_tradeoff`
   and `escalate` all validate — and nothing reads them. `auto_route` is only
   referenced in a mutual-exclusion check. `/api/llm/routers` returns a
   hardcoded empty envelope. Decision #6 makes routing dormant for *profiles*;
   it does not obviously say a caller passing `auto_route` should get silent
   default-order behavior. **Confirm this is intended**, or reject these
   fields with a 400 so the degradation is loud.

2. **Budget over-reserves on unpinned calls.** `orchestration/budget.py` takes
   `max(project(...) for provider in context.candidates)`. With no explicit
   provider or profile, `candidates` is *every configured provider*, so every
   request reserves the most expensive one's projected cost. Legacy projected
   against the selected provider. Net: 402s on requests legacy admitted. The
   comment shows it is deliberate, but it is an admission-behavior change
   inside an equivalence-first move.

3. **Pin-mismatch error envelope differs.** `provider_call.py` raises the
   `chat profile '…' expected model '…'` `ProviderError` *inside* the retry
   loop, where it is swallowed into `attempts` and re-surfaces as a generic
   `HTTPException(503, "all providers unavailable…")`. Legacy returned the
   specific message. `profile_pin_unverified` has no counterpart anywhere.

4. **Reservation leak.** If the process dies between `admit` and `reconcile`,
   rows stay `state='reserved'` and count against the ceiling — permanently
   for `period: lifetime` policies. No sweeper, no TTL. This *under*-spends,
   so it does not violate the exit gate. Note it; don't block on it.

5. **`GET /api/llm/budget`** calls `budget.describe()` → `policies()` → SQLite
   **directly on the event loop**, unlike every sibling handler. One-line fix,
   WP E #2.

---

## 4. Test coverage — 31 green is misleading

`tests/test_llm.py` is 88 lines and holds **four** tests. Against the plan's
done-conditions:

| Required | Status |
| --- | --- |
| §6: *a test proves stage 9 runs even on a retry/failover path* | ✅ `test_stage_nine_runs_after_retry_and_failover` — genuine, asserts 2 attempts and 1 audit event |
| §8: *concurrent requests never overspend a ceiling* | ✅ `test_atomic_budget_reservations_never_admit_over_ceiling` — 20 threads × $0.01 vs $0.05 → exactly 5 admitted |
| §8: *cache miss embeds exactly once* | ✅ `test_cache_miss_reuses_lookup_embedding_for_store` |
| §9: *a test proves no chat profile resolves through a routing tier* | ⚠️ **present but does not prove it.** `test_profile_resolution_is_an_exact_pin` constructs `ProfileRegistry` from an in-memory dict and asserts `resolve()` returns what it was handed. It never calls `from_yaml`, so the real `tier`/`route` rejection branch in `profiles/__init__.py` is untested, and nothing asserts `RoutingStage` ignores `routing.yaml` |
| §5: *per-provider tests pass in isolation* | ❌ **zero** provider tests |
| §6: *each stage has unit tests* | ❌ **zero** per-stage tests |
| §7: pairwise contract test against the Plan 01 baseline | ❌ **absent** — no such test exists in the repo |
| §8: load test — slow SQLite write doesn't stall others | ❌ absent |
| §8: bounded-concurrency / latency tests | ❌ absent (`ProviderCallStage` does have a 32-slot semaphore) |

---

## 5. Process

Everything is **uncommitted in one blob** (`gateway/src/`, `gateway/config/`,
`gateway/tests/`, `pyproject.toml`, `uv.lock` all untracked; `main.py`,
`openapi.json`, `mypy.ini`, `README.md` modified). Hard rule #3 — *"Only then
start Work Package E, in separate commits. Do not fuse a fix into a move
commit."* — is violated as a matter of record regardless of intent. The WP E
work (atomic budget, `to_thread`, shared client, embedding reuse) is
indistinguishable from the move.

Unrelated: the `ingestion-pipeline` submodule shows a deleted
`INGESTION_ARCHITECTURE_REFACTOR.md` (the file now sits under `To Do/`). Not
Plan 04's doing.

---

## 6. §9 exit gate — item by item

| # | Gate | |
| --- | --- | --- |
| 1 | Every provider has its own package, no provider logic in shared files | ⚠️ packages exist; **coverage incomplete** (B3). `providers/http.py` holds shared transport only — acceptable |
| 2 | No HTTP route contains the complete orchestration pipeline | ✅ |
| 3 | Every preserved JSON and streaming contract passes, verified pairwise | ❌ streaming **fails** (B1); JSON **unverifiable** (B2) |
| 4 | Concurrent budget admission cannot overspend | ✅ implemented **and** tested |
| 5 | Provider clients reused and closed cleanly | ✅ |
| 6 | Semantic-cache miss embeds at most once | ✅ implemented **and** tested |
| 7 | Every profile pins exact provider+model, unchanged; test proves no tier | ⚠️ pins verified byte-identical; **the test doesn't prove the stated property** (§4) |
| 8 | `routing.yaml` present, intact, unwired | ✅ `diff`-identical, zero references |
| 9 | `glc_v5/glc/client.py` still exists, imports cleanly, no SDK built | ✅ no `gateway/sdk/` exists |
| 10 | No domain outside `llm/` imports `LLMService` / `get_llm_service` | ✅ |
| 11 | `glc_v5/` untouched, submodule pointer unchanged | ✅ |

**7 pass · 3 partial · 1 fail.**

---

## 7. Recommended order to close

1. **Build real streaming.** Port the incremental SSE parsers from
   `providers.py:218,590` and Gemini/Ollama, wire `provider.stream()` into a
   streaming pipeline path, restore `tool_call_delta`, mid-stream `error`, and
   `profile_pin_unverified`. Blocker B1.
2. **Get Plan 01 to emit SSE + JSON response fixtures**, then write the
   pairwise contract test as a committed test — not an ad-hoc script. B2.
3. **Per-provider checklists**, then close them: Gemini `$ref` inlining +
   thinking knob first (it silently breaks structured output today), then
   Ollama prompted-tools, then Anthropic `cache_control`, then the OpenAI
   Responses-API path. B3.
4. **Decide `cache_system` / `auto_route` / `cost_quality_tradeoff` /
   `escalate`**: implement, or 400 on them. Silent ignore is the worst option.
5. **Fix the budget projection** to project against the selected provider, and
   restore the specific pin-mismatch envelope.
6. **Backfill tests**: per-stage, per-provider, a `from_yaml`-based profile
   test that actually exercises the `tier`/`route` rejection, and the load test.
7. **Re-commit as a series** — move commits first, then one WP E commit per
   fix. Cannot be recovered retroactively, but sets the pattern for Plans 05–07.
