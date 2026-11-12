# LLM Gateway V7 — Refactor Notes

## 0.3.0 — Image input

- Canonical text/image content blocks are translated to the native Anthropic,
  OpenAI, Gemini, and Ollama request shapes.
- Added the cloud-pinned `highlight-photo-summary-v1` profile and the strictly
  local `cover-classification-v1` profile, pinned to
  the installed multimodal `gemma4:12b` through `cover-vision-local`.
- Added per-provider `images` capability reporting and image-aware selection.
- Known limitation: chat token estimates still count base64 image payload
  characters, so image calls can be substantially over-estimated.

**Date:** 2026-06-24  
**Scope:** Gateway now supports Gemini, OpenAI, Anthropic, and Ollama for chat. Embeddings remain Ollama + Gemini only.

---

## Overview

The gateway previously supported a larger provider matrix plus an LLM-based tier classifier that routed requests to TINY/LARGE/HUGE worker pools. That router/UI layer is gone. The current design is:

- **Gemini**, **OpenAI**, and **Anthropic** as cloud chat providers
- **Ollama** retained for local chat (`gemma4:12b`) and embeddings (`nomic-embed-text`)
- No LLM router logic
- Chat uses the first selectable provider in `LLM_ORDER` and does not fail over after a runtime error
- No web UI

---

## Provider Changes

### Active providers

| Registry key | Backend | Model |
|---|---|---|
| `gemma` | Ollama | `gemma4:12b` (override: `OLLAMA_MODEL`) |
| `gemini-cheap` | Gemini API | `gemini-2.0-flash-lite` (override: `GEMINI_CHEAP_MODEL`) |
| `gemini-flash` | Gemini API | `gemini-2.5-flash` (override: `GEMINI_FLASH_MODEL`) |
| `gemini-pro` | Gemini API | `gemini-2.5-pro` (override: `GEMINI_PRO_MODEL`) |
| `openai-cheap` | OpenAI API | `gpt-5.4-nano` (override: `OPENAI_CHEAP_MODEL`) |
| `openai-mini` | OpenAI API | `gpt-5.4-mini` (override: `OPENAI_MINI_MODEL`) |
| `openai-pro` | OpenAI API | `gpt-5.5` (override: `OPENAI_PRO_MODEL`) |
| `anthropic-haiku` | Anthropic API | `claude-haiku-4-5` (override: `ANTHROPIC_HAIKU_MODEL`) |
| `anthropic-sonnet` | Anthropic API | `claude-sonnet-4-6` (override: `ANTHROPIC_SONNET_MODEL`) |
| `anthropic-opus` | Anthropic API | `claude-opus-4-8` (override: `ANTHROPIC_OPUS_MODEL`) |

Each vendor block is independently controlled by API key presence and `ENABLE_*` env toggles. The chat registry loads only providers whose vendor block is enabled and configured.

### Default provider-selection order

`gemma → gemini-cheap → gemini-flash → gemini-pro → openai-cheap → openai-mini → openai-pro → anthropic-haiku → anthropic-sonnet → anthropic-opus`

Override at runtime with the `LLM_ORDER` environment variable (comma-separated). Chat selects the first provider that passes capability/context/rate-state checks, then makes exactly one runtime attempt.

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

Active shortcuts include:

| Shortcut(s) | Resolves to |
|---|---|
| `gemma`, `local`, `o` | `gemma` |
| `cheap`, `lite`, `gemini-cheap` | `gemini-cheap` |
| `flash`, `g`, `gem`, `gemini`, `gemini-flash` | `gemini-flash` |
| `pro`, `gpro`, `gemini-pro` | `gemini-pro` |
| `openai-cheap`, `oai-cheap` | `openai-cheap` |
| `openai-mini`, `oai-mini` | `openai-mini` |
| `openai-pro`, `oai-pro`, `oai` | `openai-pro` |
| `anthropic-haiku`, `haiku` | `anthropic-haiku` |
| `anthropic-sonnet`, `sonnet` | `anthropic-sonnet` |
| `anthropic-opus`, `opus` | `anthropic-opus` |

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

### Active variables

```
GEMINI_API_KEY          — required for Gemini tiers
GEMINI_CHEAP_MODEL      — default: gemini-2.0-flash-lite
GEMINI_FLASH_MODEL      — default: gemini-2.5-flash
GEMINI_PRO_MODEL        — default: gemini-2.5-pro
ENABLE_GEMINI           — default: 1
OPENAI_API_KEY          — required for OpenAI tiers
OPENAI_CHEAP_MODEL      — default: gpt-5.4-nano
OPENAI_MINI_MODEL       — default: gpt-5.4-mini
OPENAI_PRO_MODEL        — default: gpt-5.5
ENABLE_OPENAI           — default: 1
ANTHROPIC_API_KEY       — required for Anthropic tiers
ANTHROPIC_HAIKU_MODEL   — default: claude-haiku-4-5
ANTHROPIC_SONNET_MODEL  — default: claude-sonnet-4-6
ANTHROPIC_OPUS_MODEL    — default: claude-opus-4-8
ENABLE_ANTHROPIC        — default: 1
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
