# Anthropic Messages adapter

This folder translates gateway requests to Anthropic's Messages API.

| File | Responsibility |
| --- | --- |
| `__init__.py` | Implements `AnthropicProvider`: system/message/image translation, native tools and results, structured output, thinking budgets, cache usage, error handling, and normalized results. |
| `schema.py` | Implements `clean()`, adapting JSON Schema to the vendor's structured-output dialect. Removes selected metadata, moves unsupported constraints into descriptions, and closes object schemas with `additionalProperties=False`. |

Consecutive turns with the same role are merged. Tool results become user-role `tool_result` blocks, and assistant calls become `tool_use` blocks. System blocks marked for caching receive ephemeral cache-control metadata. Thinking levels map to fixed token budgets; a 400 with thinking enabled triggers one request without that setting.

Final structured-output validation still uses the original schema in [orchestration](../../orchestration/README.md). `stream()` is a buffered fallback over `chat()`. Embeddings are unsupported and `embed()` raises a provider error.

The adapter uses the shared HTTP client and credentials/model instances supplied by the [registry](../README.md). It does not own global routing or accounting.
