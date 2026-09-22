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
