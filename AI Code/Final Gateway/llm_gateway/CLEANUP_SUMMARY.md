# Cleanup Summary

## Context

The gateway had grown around older V1/V2/V3 history. The current direction is
to simplify it into a small personal LLM gateway while preserving the parts that
are genuinely useful.

## Product Decisions

Keep:

- `POST /v1/chat`
- `POST /v1/embed`
- Explicit/configured provider selection
- SQLite call logs
- Rate/cooldown/backoff awareness
- Embedding status/config endpoint
- A small Python client
- Generic structured-output support for caller-provided Pydantic models
- Optional native tool-call protocol translation if the harness uses model
  emitted tool calls

Do not add:

- Gateway-owned tool registry
- Gateway-owned tool execution
- Agent loop inside the gateway
- Shared contracts package before repeated cross-project reuse exists

Remove or reduce during cleanup:

- Old V3 router/classifier history
- `auto_route` leftovers
- Web UI references
- Stale router-decision fields
- Broad historical README material
- Any compatibility path that only preserves old behavior and is not needed for
  the current gateway

## Tool-Call Clarification

The MCP server and harness own tools. The gateway should not register or execute
tools.

The only tool-related behavior worth keeping is deterministic provider protocol
translation:

```text
MCP/harness tool schema
        -> canonical gateway ToolDef
        -> provider-specific request shape
        -> provider-specific response shape
        -> canonical gateway ToolCall
        -> harness executes through MCP
```

This is useful because OpenAI, Anthropic, Gemini, and Ollama each expose native
tool/function calling differently. It is also a likely failure point, so it now
has focused offline tests.

## Structured Output Clarification

Tool input contracts belong with MCP tools.

Structured output is separate. It is for cases where the caller wants the
model's final response, extraction, classification, or decision as typed JSON.

The useful future abstraction is a generic client helper:

```python
decision = llm.structured(..., output_model=SomePydanticModel)
```

The gateway client should accept a caller-provided Pydantic model, convert its
JSON schema into `response_format`, validate the response, and return a typed
instance. The gateway should not own project-specific contracts.

## Files Added

- `AGENTS.md`
  Cleanup handoff note for future chats. It records the target scope, feature
  boundaries, and cleanup priorities.

- `CLEANUP_SUMMARY.md`
  This summary document.

- `tests/test_tool_translation.py`
  Offline unit tests for deterministic tool schema translation and returned
  tool-call normalization.

## Test Coverage Added

`tests/test_tool_translation.py` covers:

- OpenAI tool schema translation and returned `tool_calls` normalization
- Anthropic tool schema translation and returned `tool_use` normalization
- Gemini `function_declarations` translation and `functionCall` normalization
- Ollama native tool translation
- Ollama prompted fallback parsing
- Canonical assistant/tool-result turns translated back into OpenAI,
  Anthropic, and Gemini message shapes

Verified:

```text
uv run pytest -q tests/test_tool_translation.py
6 passed

uv run pytest -q tests/test_tool_translation.py tests/test_provider_registry.py
8 passed
```

Note: `uv` needed elevated filesystem permission during verification because it
uses `~/.cache/uv`. The tests themselves are offline and do not call provider
APIs.

## Recommended Cleanup Order

1. Rewrite `README.md` around the current gateway only.
2. Remove `auto_route` from `client.py` and stale docs/tests.
3. Add a lightweight `LLM.structured(...)` helper for arbitrary caller-provided
   Pydantic output models.
4. Split the large `/v1/chat` handler in `main.py` into smaller helpers.
5. Consider renaming `router.py` to something like `selection.py` or
   `provider_state.py` if it reduces confusion without too much churn.
6. Split `providers.py` by backend if provider code continues to grow.
7. Remove unused schema/database fields only after checking migration impact on
   the existing `gateway_v7.db`.
8. Keep tests focused on retained behavior: provider registry, no chat runtime
   failover after selected-provider errors, tool-call normalization, structured
   output validation/repair, embeddings, and rate-state behavior.
