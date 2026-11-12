# LLM Gateway V7 — Refactor Notes

**Date:** 2026-06-24  
**Scope:** Stripped to Gemini-only (enterprise) + Ollama (local). Removed all non-Gemini providers, routing intelligence, and the web UI.

---

## Overview

The gateway previously supported nine cloud providers (OpenAI, Anthropic, Gemini, Groq, Cerebras, NVIDIA, OpenRouter, GitHub Models) plus Ollama, with an LLM-based tier classifier that routed requests to TINY/LARGE/HUGE worker pools. All of that is gone. The new design is:

- **Gemini** as the sole cloud provider, across three cost/quality tiers
- **Ollama** retained for local chat (`gemma4:12b`) and embeddings (`nomic-embed-text`)
- No routing logic — failover is a simple ordered list
- No web UI

---

## Provider Changes

### Removed providers

| Provider | Adapter class removed |
|---|---|
| OpenAI (direct) | `OpenAIProvider` |
| OpenAI-compat base | `OpenAICompatProvider` |
| Groq | `GroqProvider` |
| Cerebras | `CerebrasProvider` |
| NVIDIA | `NvidiaProvider` |
| OpenRouter | `OpenRouterProvider` |
| GitHub Models | `GitHubProvider` |
| Anthropic | `AnthropicProvider` |

### Retained providers

| Registry key | Backend | Model |
|---|---|---|
| `gemma` | Ollama | `gemma4:12b` (override: `OLLAMA_MODEL`) |
| `gemini-cheap` | Gemini API | `gemini-2.0-flash-lite` (override: `GEMINI_CHEAP_MODEL`) |
| `gemini-flash` | Gemini API | `gemini-2.5-flash` (override: `GEMINI_FLASH_MODEL`) |
| `gemini-pro` | Gemini API | `gemini-2.5-pro` (override: `GEMINI_PRO_MODEL`) |

All three Gemini models are instantiated from a single `GEMINI_API_KEY`. If the key is absent, only `gemma` (Ollama) loads.

### Default failover order

```
gemma → gemini-cheap → gemini-flash → gemini-pro
```

Override at runtime with the `LLM_ORDER` environment variable (comma-separated).

---

## Rate Limits (router.py)

Limits updated to reflect enterprise subscription (no daily cap on Gemini):

| Provider | RPM | RPD | TPM | Max context |
|---|---|---|---|---|
| `gemma` | 9999 | 9999999 | 99999999 | 32 000 |
| `gemini-cheap` | 2000 | unlimited | 4 000 000 | 1 000 000 |
| `gemini-flash` | 1000 | unlimited | 1 000 000 | 1 000 000 |
| `gemini-pro` | 1000 | unlimited | 1 000 000 | 1 000 000 |

Previously the free-tier Gemini limits (15 RPM / 1000 RPD) were used. RPD=0 now means no daily cap.

### Shortcuts updated

Removed all OpenAI (`mini`, `4omini`, `gpt4o`, `oai`, `oaipro`, `4o`) and Anthropic (`haiku`, `sonnet`, `opus`, `a`, `ant`, `claude`) shortcuts.

Active shortcuts:

| Shortcut(s) | Resolves to |
|---|---|
| `gemma`, `local`, `o` | `gemma` |
| `cheap`, `lite`, `gemini-cheap` | `gemini-cheap` |
| `flash`, `g`, `gem`, `gemini`, `gemini-flash` | `gemini-flash` |
| `pro`, `gpro`, `gemini-pro` | `gemini-pro` |

---

## Routing Logic Removed (main.py)

The V3 LLM-based tier classifier is gone entirely. The following were deleted:

- `TIER_TO_ORDER` — mapping of TINY/LARGE/HUGE to provider order
- `ROUTER_SAMPLE_HEAD / TAIL` — prompt truncation constants
- `ROUTER_PROMPT` — the system prompt sent to the router LLM
- `_estimate_tokens()` — rough token estimator for routing
- `_build_sample()` — context window sampler
- `_tier_from_count()` — deterministic fallback tier classifier
- `_parse_tier()` — parser for TINY/LARGE/HUGE router output
- `_classify_tier()` — async function that called the router LLM and returned a `RouterDecision`
- `auto_route` branch in `/v1/chat` — the block that ran classification and selected a tier-specific candidate list
- `app.state.router_providers` and `app.state.router_pool` — the router LLM pool
- `RouterPool` class in `router.py` — the failover ring for router LLMs
- `DEFAULT_ROUTER_ORDER` constant
- `build_router_providers()` in `providers.py` — built the gemma-small router instance
- `ROUTER_DEFAULTS` constant

`/v1/routers` endpoint removed (exposed router pool status; no longer relevant).

---

## Schema Changes (schemas.py)

### Removed

- `RouterDecision` model — carried tier, estimated tokens, router provider, latency; echoed on responses when `auto_route` was used
- `auto_route` field on `ChatRequest` — `Literal["perception", "memory", "decision"]`; triggered LLM classification
- `router_decision` field on `ChatResponse` — `Optional[RouterDecision]`

### Unchanged

All other fields on `ChatRequest` and `ChatResponse` are intact: `messages`, `prompt`, `system`, `provider`, `model`, `max_tokens`, `temperature`, `stream`, `tools`, `tool_choice`, `cache_system`, `reasoning`, `response_format`, `tool_calls`, `stop_reason`, token counts, `parsed`, `attempted`.

---

## Web UI Removed

The following were deleted:

| Deleted | Was |
|---|---|
| `static/dashboard.html` | Live metrics dashboard (provider status, call log, token usage) |
| `static/help.html` | API reference / usage guide |
| `static/` directory | Entire static assets folder |
| `app.mount("/static", ...)` | FastAPI StaticFiles mount |
| `GET /` | Served `dashboard.html` |
| `GET /help` | Served `help.html` |

The `fastapi.staticfiles.StaticFiles` import and `FileResponse` import were also removed from `main.py`.

---

## Embeddings (unchanged)

No changes to `embedders.py`. Embedding failover is:

1. **Ollama** — `nomic-embed-text` (local, 768-dim)
2. **Gemini** — `gemini-embedding-001` (768-dim, matches Ollama dimension)

Both providers pin to 768-dim so a FAISS index built on one remains valid if the other takes over.

---

## Environment Variables

### No longer used

```
OPENAI_API_KEY, OPENAI_MINI_MODEL, OPENAI_PRO_MODEL
ANTHROPIC_API_KEY, ANTHROPIC_HAIKU_MODEL, ANTHROPIC_SONNET_MODEL, ANTHROPIC_OPUS_MODEL
ROUTER_ORDER
OLLAMA_SMALL_MODEL, OLLAMA_LARGE_MODEL, OLLAMA_ROUTER_MODEL
```

### Active variables

```
GEMINI_API_KEY          — required for Gemini tiers
GEMINI_CHEAP_MODEL      — default: gemini-2.0-flash-lite
GEMINI_FLASH_MODEL      — default: gemini-2.5-flash
GEMINI_PRO_MODEL        — default: gemini-2.5-pro
OLLAMA_URL              — default: http://localhost:11434
OLLAMA_MODEL            — default: gemma4:12b
EMBED_OLLAMA_MODEL      — default: nomic-embed-text
LLM_ORDER               — comma-separated failover order override
GATEWAY_V7_PORT         — default: 8107
```

---

## Active API Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/chat` | Chat completion (stream or non-stream) |
| POST | `/v1/embed` | Text embedding |
| GET | `/v1/providers` | List providers, shortcuts, limits, models |
| GET | `/v1/capabilities` | Per-provider capability flags |
| GET | `/v1/status` | Live rate state + today's call stats |
| GET | `/v1/embedders` | Embedder status and config |
| GET | `/v1/calls` | Recent call log |

### Removed endpoints

| Method | Path | Reason |
|---|---|---|
| GET | `/` | Dashboard UI removed |
| GET | `/help` | Help UI removed |
| GET | `/v1/routers` | Router pool removed |
