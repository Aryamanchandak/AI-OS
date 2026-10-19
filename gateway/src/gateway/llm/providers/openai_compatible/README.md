# OpenAI-compatible API adapter

`__init__.py` implements `OpenAICompatibleProvider` for custom chat-completions endpoints. It is retained for future integrations and is not constructed by the [registry](../README.md). Callers supply its name, key, default model, base URL, and shared HTTP client.

The adapter builds chat-completions payloads with `max_tokens`, system messages, function tools, structured response formats, and optional `reasoning_effort`. It normalizes result text, tool arguments, stop reasons, token usage, and cached-input usage into gateway value objects. It has an embeddings method, but declared capabilities currently leave `embeddings=False`, so the service's normal embedding loop skips these instances.

Transport failures become normalized `ProviderError` exceptions. JSON calls use `providers/http.py`. The native [OpenAI adapter](../openai/README.md) is separate because its request dialect differs. Global budgets, retries, and audit belong to [orchestration](../../orchestration/README.md).
