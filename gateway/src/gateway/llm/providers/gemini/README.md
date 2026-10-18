# Gemini adapter and context caching

This folder implements Google's generateContent and embedContent dialects behind the common gateway provider interface.

| File | Responsibility |
| --- | --- |
| `__init__.py` | Implements `GeminiProvider`, message/image/function translation, reasoning settings, response-schema translation, usage normalization, embeddings, and buffered streaming. |
| `schema.py` | Inlines local `$ref` definitions with recursion protection, then strips fields rejected by the response-schema dialect. |
| `context_cache.py` | Implements `GeminiContextCache`, which creates and reuses remote `cachedContents` resources for long cacheable system text. |

Assistant messages become `model` contents. Tool results become function responses, and tool-call `thoughtSignature` metadata is preserved for later turns. Thinking settings use model-name rules to select a level or token-budget dial. A 400 response triggers one retry with optional rejected thinking/cache settings removed as applicable.

When caching is requested and selected system text exceeds 1,000 characters, the adapter can create a remote context cache. Its local map stores resource names and expiry by model/text hash, with a one-hour default TTL. Cache creation failures fall back to inline system text. This vendor prompt cache differs from the gateway's [semantic response cache](../../cache/README.md).

`stream()` buffers `chat()` before yielding text and publishes the completed result for accounting. `embed()` forwards the requested retrieval task type. Registry construction supports numbered Gemini credential slots, falling back to the legacy single-key variable when no numbered keys are configured. See [provider registry](../README.md).
