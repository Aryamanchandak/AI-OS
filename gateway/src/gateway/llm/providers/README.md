# Provider adapters

This folder defines the common provider contract, builds configured instances, and translates between gateway-neutral requests/results and vendor APIs. Adapters share the application's HTTP client; orchestration owns request-wide policy.

## Shared files

| File | Responsibility |
| --- | --- |
| `base.py` | Defines the provider protocol, capabilities, normalized results/usage/errors, the tool-delta marker, and buffered streaming helpers. |
| `registry.py` | Constructs credential-enabled cloud instances and YAML-configured local models, applies capability overrides, and exposes deterministic explicit/ordered candidate lookup. |
| `capabilities.py` | Resolves model-dependent feature flags using name hints and adapter defaults for diagnostics. |
| `content.py` | Normalizes text/system/image blocks, tool definitions, arguments, and tool-result objects for adapter translation. |
| `http.py` | Posts JSON with common timeout, HTTP error, retryability, and response-object checks. |
| `__init__.py` | Re-exports the provider protocol and common value objects. |

## Adapter folders

- [openai](openai/README.md): native OpenAI request dialect.
- [anthropic](anthropic/README.md): Messages API and schema adaptation.
- [gemini](gemini/README.md): generateContent, embeddings, schemas, and remote context caching.
- [ollama](ollama/README.md): local models, images, native/prompted tools, and embeddings.
- [openai_compatible](openai_compatible/README.md): compatible cloud endpoints and incremental SSE parsing.

Registry membership means an instance was configured, rather than that a live health probe succeeded. Candidate selection follows registry order unless a provider is explicitly pinned. Most adapters stream via a completed, buffered chat result; only the compatible family parses incremental SSE. Embedding selection follows declared capabilities: native OpenAI and compatible adapters have embedding methods but currently do not advertise that capability.

See [orchestration](../orchestration/README.md) for retries, profile verification, budgets, finalization, and streaming differences. The original migration checklist and smoke instructions are preserved below; their coverage claims should be read alongside the current behavior described above.

---

# LLM provider migration map

Every adapter uses the lifespan-owned `httpx.AsyncClient`; no adapter owns a
per-call client. Global routing, budgets, retry/failover, caching, metering,
and audit remain in `gateway.llm.orchestration`.

## Coverage checklist

- OpenAI: credentials/model pins, chat translation, image blocks, native tools,
  structured output, reasoning effort, usage normalization, error normalization,
  SSE adapter, embeddings.
- Anthropic: credentials/model pins, Messages translation, system prompt,
  image/tool dialect, structured output, thinking budgets, cache-token usage,
  error normalization, SSE adapter.
- Gemini: numbered and legacy key aliases, generateContent translation, inline
  images, functions, response schema, thinking capability, usage normalization,
  SSE adapter, embeddings.
- Ollama: all entries from `local_models.yaml`, exact profile-owned pins,
  local vision/tool/JSON dialects, `think:false`, usage normalization, SSE
  adapter, embeddings.
- OpenAI-compatible: Groq, Cerebras, NVIDIA, OpenRouter, and GitHub credentials,
  base URLs, model aliases, chat/tools/structured/reasoning translation, usage,
  error normalization, SSE adapter, embeddings where the endpoint supports it.

## Live smoke

Set the provider's existing environment variable and start Gateway. Then call
`POST /api/llm/chat` with an explicit provider and model. Use the same body with
`"stream": true` to inspect SSE framing. For embeddings, call
`POST /api/llm/embed`. Useful credential variables are `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (or numbered `_1`…`_10`),
`GROQ_API_KEY`, `CEREBRAS_API_KEY`, `NVIDIA_API_KEY`,
`OPEN_ROUTER_API_KEY`, and `GITHUB_ACCESS_TOKEN`. Ollama uses `OLLAMA_URL`.

Live calls are intentionally not part of the offline test suite.
