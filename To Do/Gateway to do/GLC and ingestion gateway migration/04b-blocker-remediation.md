# Plan 04b — Blocker Remediation

**Worked:** 2026-09-22 · **Against:** `04a-verification-report.md` §2 (B1, B2, B3)

LLM suites: **60 passed, 0 failed** —
`test_llm` 6 · `test_llm_streaming` 13 · `test_llm_providers` 33 ·
`test_llm_orchestration` 3 · `test_llm_contract` 5. Plus
`test_platform_security_control` 17 and `test_foundation` green.

The full `tests/` run shows 161 failures, **all** of them in `tests/channels/`
and `tests/voice/` — Plan 05 suites that landed in the tree while this work was
in progress. Nothing under `src/gateway/llm/` is implicated; see §5.

---

## 0. A correction to the report, from the source

The report's §7.1 remediation is wrong for four of the five provider packages,
and the fix is much narrower than it implies.

```
$ grep -n 'async def stream' glc_v5/glc/providers.py glc_v5/glc/direct_providers.py
glc_v5/glc/providers.py:218    BaseProvider.stream          — buffered fallback
glc_v5/glc/providers.py:590    OpenAICompatProvider.stream  — real incremental SSE
```

`direct_providers.py` defines **no** `stream` at all. Cross-referenced against
`build_providers()` (`providers.py:1320`), legacy streaming is:

| Provider | Legacy streaming behaviour |
| --- | --- |
| groq, cerebras, nvidia, openrouter, github | incremental `delta` frames, `[[TOOL_CALL_DELTA]]`, model confirmed from chunk `d["model"]` |
| **openai-\***, **anthropic-\***, **gemini_N**, **ollama** | `BaseProvider.stream` — one frame with the whole text, model published via `result_sink` |

So "port the incremental SSE parsers from `providers.py:218,590` and
Gemini/Ollama" asks for parsers that do not exist. For Anthropic, Gemini, Ollama
and OpenAI the single-frame stub **was already legacy-equivalent**. What was
genuinely missing is smaller and sharper:

- nothing called `provider.stream()` at all
- no `result_sink` equivalent, so no streamed pin check
- no `tool_call_delta` frame, no mid-stream `error` frame
- no `profile_pin_unverified` flag
- **stage 9 would have fired before the first byte** (see §1)

---

## 1. B1 — streaming: **closed**

### The trap the report did not name

`LLMPipeline.run` fires `finalization` from a `finally:` and then returns. Had
the route simply returned a `StreamingResponse` wrapping that, stage 9 would
have metered the call *before a single byte flowed* — an audit row with no
result and a budget reservation reconciled to zero. Legacy meters at the **end
of the generator** (`meter.record` inside `gen()`, including in its `except`).

`pipeline.py` now has `run_stream`, which runs stages 1–6 eagerly and returns a
generator that owns stages 7 and 9:

- **Stages 1–6 await before the response is committed**, so a 400/402/503 from
  validation, budget or routing still reaches the caller as a normal JSON error
  rather than as an error frame inside a 200.
- **Stage 9 runs in the generator's `finally`.** Client disconnect arrives as
  `GeneratorExit`, so a hang-up still meters and still reconciles the
  reservation — which is the cancellation/disconnect item the report listed as
  broken, obtained for free rather than built separately.
- `GeneratorExit` / `CancelledError` are caught *before* the general handler,
  because yielding into a closing generator raises.

### Frames restored, byte-for-byte

`orchestration/streaming.py` owns frame encoding so the shapes are testable
independently of the route. Key *order* is part of the contract —
`json.dumps` preserves insertion order and callers parse raw bytes:

| Frame | Shape |
| --- | --- |
| text | `{"provider": …, "delta": …}` |
| tool call | `{"provider": …, "tool_call_delta": "<JSON string>"}` — stays a string, as legacy sends it |
| error | `{"error": …}` — **no** provider key, matching legacy |
| done | `{"done": true, "provider": …, "model": …, "profile": …}` |
| pin unverified | `profile_pin_unverified: true` appended to the done frame |
| pin mismatch | error frame, then `return` — **no** done frame |

### A crash the report did not reach, found while building this

On a semantic-cache hit, `CacheLookupStage` fills `context.output`; `RoutingStage`
and `BudgetReservationStage` then both early-return, so **`context.candidates`
stays empty**. A streaming path that assumed a candidate would raise `IndexError`
inside the generator body — i.e. *after* the 200 and headers were committed,
giving the client a truncated stream rather than an error.

Reachable in production: `skip_when_stream` defaults True but is operator-set
(`cache.yaml`), so any deployment with `skip_when_stream: false` hits it.

Legacy settles the right behaviour — `chat.py:691` returns the stored body
`return out` regardless of `req.stream`. So **a cache hit answers a streaming
request with JSON, not SSE frames**. `run_stream` now returns `dict | AsyncIterator`
and the route branches on it. Both the streaming and non-streaming paths share
one `_finish()` tail, so they cannot drift apart again.

Covered by `test_cache_hit_on_a_streaming_request_answers_with_json_not_frames`.

### One deliberate divergence, stated

Legacy meters streamed calls with an empty `Usage()`, so every streamed call
books zero cost and its reservation reconciles to zero. Where the provider hands
the real usage back (the buffered family — four of five packages), stage 9 now
meters it truthfully via `result_sink["result"]`. Incremental providers still
report zero, because no usage exists to report.

This changes metering numbers versus legacy. I took it because hard rule #4
makes stage 9 a program-wide invariant, and logging a known cost as zero
defeats the budget reconciliation that Work Package E #1 exists to protect.
It does not touch SSE frame bytes. **Flagging it as a decision, not a fix** — if
you want strict legacy equivalence here, it is a one-line revert.

Full surface of that decision: `FinalizationStage` passes
`count=result is not None` to `budget.reconcile`, so buffered streams now count
toward the call ceiling and incremental ones still do not. The same one-line
revert covers both effects.

### Contract guard against "fixing" too much

Migrated `OpenAIProvider` previously inherited `OpenAICompatibleProvider`. Once
the compatible family got a real incremental parser, `openai-*` would have
started streaming incrementally where legacy emitted one frame — a silent
contract change made *while claiming to fix streaming*. `OpenAIProvider` now
overrides `stream()` with the buffered path explicitly, with a comment saying
why.

**Tests:** `tests/test_llm_streaming.py`, 12 tests — frame shapes, exact done-frame
bytes, tool-call deltas, mid-stream error, pin mismatch, unverified pin,
stage-9-after-not-before, disconnect metering, pre-stream rejection.

---

## 2. B3 — provider migration: **closed**

Every row of the report's gap table now has a counterpart and a test.

| Gap | Migrated to | Test |
| --- | --- | --- |
| `_gemini_inline_refs` / `_gemini_clean_schema` | `providers/gemini/schema.py` | `$ref` inlining, self-referential termination, key stripping |
| `_gemini_supports_thinking` / `_gemini_thinking_knob` | `providers/gemini/__init__.py` | knob per model; `reasoning_applied` no longer lies on flash-lite |
| Gemini context `cache_store` | `providers/gemini/context_cache.py` | ported from `glc_v5/glc/cache/gemini.py`; soft-fails to inline |
| `ToolCall.provider_meta` (thoughtSignature) | Gemini chat, both directions | echo on send, surface on receive |
| `_prompted_tool_system` / `_parse_prompted_tool_call` / `_ollama_native_tools` | `providers/ollama/tools.py` | native vs prompted dialect, parse-from-prose, images field |
| Anthropic `cache_control` / `_flatten_system` | `providers/anthropic/__init__.py` | per-block markers, `cache_system` flag |
| `anthropic_clean_schema` | `providers/anthropic/schema.py` | constraints restated as prose, not dropped |
| `model_capabilities()` per-model | `providers/capabilities.py` | per-model reasoning/vision resolution |

### OpenAI — decision #1's whole point

The report called `direct_providers.OpenAIProvider` a "Responses API" adapter.
It is not — it posts to `/chat/completions`. But it differs from the compatible
adapter in four ways that the 10-line subclass got wrong:

- **`max_completion_tokens`, not `max_tokens`** — current OpenAI models *reject*
  `max_tokens`. The inherited adapter was sending a field that 400s.
- `parallel_tool_calls: true`
- forced tool choice as `{"type": "function", "function": {"name": …}}`
- `reasoning_effort` gated on `o1/o3/o4/gpt-5`, not on the caller merely asking

`providers/openai/` is now a real package.

**Why gate item 1 still holds.** Two shared files sit beside the packages.
`providers/content.py` is provider-agnostic content-block normalization — it
names no vendor, the same category the report already accepted `providers/http.py`
in as "shared transport only". `providers/capabilities.py` *does* contain
provider-named branches (`provider == "cerebras"`, `openai-`/`anthropic-`), but
what it decides is cross-provider *reporting resolution*, not how to talk to any
API; legacy has the identical shape at module level in `providers.py:1253`. No
package can be swapped out by editing either file, which is the property the
gate is protecting.

### The `model_capabilities()` row is ✅ for resolution, not for wire shape

Per-model resolution is genuinely fixed. The endpoint's **keys** still diverge
from legacy, and this is the most concrete instance of the B2 residual in §3:

| Legacy `/v1/capabilities` per provider | Migrated |
| --- | --- |
| `tools, caching, reasoning, structured, parallel_tools, vision, images, model, max_ctx, rpm, rpd` | `model, streaming, tools, vision, structured_output, reasoning, embeddings, max_ctx` |

`caching`, `parallel_tools`, `images`, `rpm`, `rpd` are absent; `structured` is
renamed `structured_output`; `streaming` and `embeddings` are new. This predates
this work and the pairwise contract test provably cannot catch it (no
`response_model` on either side). `rpm`/`rpd` come from legacy's `LIMITS` table,
which lives in the dormant routing module — so closing this needs a decision
about where rate limits live, not just a rename.

### `cache_system` fixed as a side effect

Legacy passes `cache_system=bool(req.cache_system)` to `provider.chat()`
(`chat.py:946`). It now does here too, so one of the four silently-ignored
fields in report §3.1 is genuinely implemented rather than merely accepted.

**Tests:** `tests/test_llm_providers.py`, 33 tests, one per dialect behaviour.

---

## 3. B2 — contract verification: **partially closed, residual named**

`tests/test_llm_contract.py` is now a committed test rather than an ad-hoc
script, covering the pairwise old→new mapping:

- every mapped route exists at its new path
- methods preserved
- request-body schemas resolve identically against the Plan 01 baseline
- nothing LLM-domain in the baseline is unaccounted for (non-LLM prefixes are
  listed explicitly by owning plan, so a surprise addition fails rather than
  being swept up)
- the `/v1` alias is the *same router object*, deprecated, so Plan 07 can find it

**What it still cannot do, unchanged from the report:** compare response bodies.
No legacy LLM route declares a `response_model`, so the baseline carries
`"schema": {}` for every 200 on both sides. Closing that needs recorded response
fixtures, **which Plan 01 owes and which do not exist in this tree**
(`migration/baseline/contracts/` holds only the two OpenAPI dumps).

That residual is not hypothetical — `/api/llm/capabilities` diverges today in
five keys (§2). Expect the fixtures to surface more of the same class.

`tests/test_llm_streaming.py` covers the SSE half of the contract directly
instead of through OpenAPI, which is stronger than a fixture diff for that half.

**Exit gate item 3 should stay marked partial** until Plan 01 lands JSON
response fixtures. Streaming is no longer failing; JSON remains unverifiable.

---

## 4. Riders taken from §3 (below-blocker, but they came along)

- **§3.3 pin-mismatch envelope** — was raised as `ProviderError` *inside* the
  retry loop, swallowed into `attempts`, re-surfacing as a generic
  `503 all providers unavailable`. Now an `HTTPException(500)` carrying the
  specific message on both the streaming and non-streaming paths.
- **§3.5 `GET /api/llm/budget`** — `describe()` was hitting SQLite on the event
  loop, unlike every sibling handler. Now `asyncio.to_thread`.

## Not taken — these need your call, not mine

- **§3.1 `auto_route` / `cost_quality_tradeoff` / `escalate`.** Still accepted
  and ignored. They are routing-tier fields, and decision #6 forbids wiring
  `routing.yaml`, so "implement" is off the table. The report's alternative —
  400 on them — is a caller-visible behaviour change that turns today's silent
  default-order into a hard failure. That is a product decision; it is also §3,
  not a blocker. **Tell me which and I'll do it.**
- **§3.2 budget over-reservation** on unpinned calls. Deliberate per its comment,
  and changing it changes admission behaviour.
- **§3.4 reservation leak.** The report says note, don't block. Noted.

---

## 5. Two things you should know

1. **Plan 05 is landing in this tree concurrently.** `src/gateway/channels/`,
   `src/gateway/voice/`, `tests/channels/` and `tests/voice/` appeared during
   this session. They currently contribute **161 failing tests** and 11 mypy
   errors. Zero of either are under `src/gateway/llm/` — my changes are confined
   to `src/gateway/llm/` and the five `tests/test_llm*` files. Worth confirming
   Plan 05 knows, and worth keeping the two efforts on separate branches.
2. **Nothing is committed.** Report §5's point stands and cannot be recovered
   retroactively, but this work *is* separable into the three commits hard rule
   #3 wants — B3 providers, B1 streaming, B2 contract tests — and I have not
   committed anything without being asked. Say the word.

## Exit gate delta

| # | Gate | Before | Now |
| --- | --- | --- | --- |
| 1 | Provider packages complete | ⚠️ partial | ✅ |
| 3 | JSON + streaming contracts | ❌ fail | ⚠️ streaming ✅, JSON still blocked on Plan 01 |
| 7 | Profile pin test proves no tier | ⚠️ partial | ⚠️ unchanged — §4 work, not a blocker |

**Was 7 pass · 3 partial · 1 fail → now 8 pass · 3 partial · 0 fail.**
