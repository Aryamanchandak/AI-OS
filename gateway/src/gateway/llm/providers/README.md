# Provider adapters

This folder defines the common provider contract, builds configured instances, and translates gateway requests/results into vendor APIs. Adapters share the application's HTTP client; orchestration owns request-wide policy.

## Configuration

The registry exposes one `openai` provider when `OPENAI_API_KEY` is set, one `anthropic` provider when `ANTHROPIC_API_KEY` is set, and every local entry from `config/local_models.yaml`. No other cloud credentials register providers.

Default candidate order is `openai`, `anthropic`, then the local entries in YAML order, skipping hosted providers without credentials. The default hosted models are `gpt-5.4-nano` and `claude-haiku-4-5`; override them with `OPENAI_MODEL` and `ANTHROPIC_MODEL`. Ollama uses `OLLAMA_URL`, with optional model overrides declared in `local_models.yaml`.

Choose a model per call with `provider` and `model`, or define a named profile in `config/profiles.yaml`. Profiles use the real provider name, such as `anthropic`, plus an exact model. To add another model from an existing provider, add its exact price to `config/pricing.yaml`, then select it in a request, profile, or default-model environment variable. Unknown models remain explicitly unpriced; local defaults and profiles have explicit zero API token prices.

For example:

```json
{"provider": "anthropic", "model": "claude-sonnet-4-6", "prompt": "Summarize this text."}
```

Configured membership does not establish live availability. Candidate selection follows registry order unless a provider is explicitly pinned.

## Shared files

| File | Responsibility |
| --- | --- |
| `base.py` | Provider protocol, capabilities, normalized results/usage/errors. |
| `registry.py` | Constructs credential-enabled hosted providers and YAML-configured local models, applies capability overrides, and exposes explicit/ordered candidate lookup. |
| `capabilities.py` | Resolves model-dependent feature flags using name hints and adapter defaults for diagnostics. |
| `content.py` | Normalizes text/system/image blocks, tools, arguments, and tool-result objects. |
| `http.py` | Posts JSON with common timeout, HTTP error, retryability, and response-object checks. |
| `__init__.py` | Re-exports the provider protocol and common value objects. |

## Adapters

- [openai](openai/README.md): native OpenAI request dialect, structured output, tools, reasoning, and usage.
- [anthropic](anthropic/README.md): Messages API, schema adaptation, tools, thinking, and prompt caching.
- [ollama](ollama/README.md): local models, images, native/prompted tools, and embeddings.
- [openai_compatible](openai_compatible/README.md): retained support for custom compatible endpoints; not registered by default.

Embedding selection follows declared capabilities. Native OpenAI and compatible adapters have embedding methods but do not currently advertise that capability.

See [orchestration](../orchestration/README.md) for retries, profile verification, budgets, and finalization. Live calls are excluded from the offline test suite; use `POST /api/llm/chat` with an explicit provider/model to probe a configured service, and `POST /api/llm/embed` for embeddings.
