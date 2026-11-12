# Anthropic native structured output — 2026-07-29

`AnthropicProvider.chat()` now honors schema-backed `response_format` through
Anthropic's native `output_config.format` API. The previous adapter advertised
`structured=True` but silently deleted the format before making the request.

The raw HTTP adapter mirrors Anthropic's SDK behavior:

- unsupported grammar constraints such as numeric, string, and array bounds
  are removed from the provider copy and carried into descriptions;
- object schemas are closed with `additionalProperties: false`;
- the caller's original schema remains untouched and is validated by the
  gateway after the provider returns;
- schema-less structured formats fail loudly rather than degrading to ordinary
  chat.

Native direct-output constraints preserve the gateway's existing
`text -> jsonschema validation -> parsed` flow. No synthetic tool call or
`main.py` tool-branch exception was added.

Package version: `llm-gateway-v7` 0.2.1.

Verification:

```text
23 passed, 10 deselected
```

A bounded live `claude-sonnet-4-6` request returned schema-constrained JSON and
gateway-populated `parsed` output. The merged ingestion pipeline's complete
batch-extraction smoke then passed using its real Pydantic schema.

Anthropic reference:
https://platform.claude.com/docs/en/build-with-claude/structured-outputs
