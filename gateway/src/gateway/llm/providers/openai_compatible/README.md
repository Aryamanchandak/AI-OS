# OpenAI-compatible API adapter

`__init__.py` implements `OpenAICompatibleProvider` for configured Groq, Cerebras, NVIDIA, OpenRouter, and GitHub endpoints. The [registry](../README.md) supplies each instance's name, key, default model, base URL, and shared HTTP client.

The adapter builds chat-completions payloads with `max_tokens`, system messages, function tools, structured response formats, and optional `reasoning_effort`. It normalizes result text, tool arguments, stop reasons, token usage, and cached-input usage into gateway value objects. It has an embeddings method, but declared capabilities currently leave `embeddings=False`, so the service's normal embedding loop skips these instances.

Unlike the other adapter families, `stream()` parses vendor SSE incrementally. It yields text as received and marks tool-call deltas with the shared internal marker for the pipeline to translate. Echoed model names are placed in the result sink for profile confirmation. It does not currently assemble a final `ProviderResult` or usage totals from that stream.

Transport failures become normalized `ProviderError` exceptions. Non-streaming JSON calls use `providers/http.py`. The native [OpenAI adapter](../openai/README.md) is separate because its request dialect differs. Global budgets, retries, audit, and caching belong to [orchestration](../../orchestration/README.md).
