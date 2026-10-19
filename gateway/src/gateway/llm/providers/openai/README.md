# Native OpenAI adapter

`__init__.py` implements `OpenAIProvider`, translating common gateway messages into OpenAI chat-completions requests and responses. It handles system text, images, assistant tool calls, tool results, structured response formats, reasoning effort, token usage, cached-input usage, and provider errors.

The adapter uses `max_completion_tokens`, native function definitions, parallel tool calls, and an object form for forced tool selection. Reasoning effort is applied only for model names matching its configured family hints. Prompt caching is automatic on this surface, so `cache_system` does not add a vendor dial.

`chat()` returns a completed, normalized `ProviderResult`.

`embed()` implements the OpenAI embeddings request, but this adapter's declared capabilities currently leave `embeddings=False`. The service's normal embedding candidate loop therefore skips these instances.

The [provider registry](../README.md) creates named OpenAI instances when the credential environment variable is present, using the shared application HTTP client. Cross-provider retries, budgets, cache, and call logging belong to [orchestration](../../orchestration/README.md).
