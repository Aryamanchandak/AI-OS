# Provider adapters

This folder defines the common provider contract and builds configured instances. Talking to vendors is any-llm's job: `llm.py` is the only file that imports it. Orchestration owns request-wide policy, including retries.

## Configuration

The registry exposes one `openai` provider when `OPENAI_API_KEY` is set, one `anthropic` provider when `ANTHROPIC_API_KEY` is set, and every local entry from `config/local_models.yaml`. No other cloud credentials register providers.

Default candidate order is `openai`, `anthropic`, then the local entries in YAML order, skipping hosted providers without credentials. The default hosted models are `gpt-5.4-nano` and `claude-haiku-4-5`; override them with `OPENAI_MODEL` and `ANTHROPIC_MODEL`. Ollama uses `OLLAMA_URL`, with optional model overrides declared in `local_models.yaml`.

Choose a model per call with `provider` and `model`, or define a named profile in `config/profiles.yaml`. Profiles use the real provider name, such as `anthropic`, plus an exact model. To add another model from an existing provider, add its exact price to `config/pricing.yaml`, then select it in a request, profile, or default-model environment variable. Unknown models remain explicitly unpriced; local defaults and profiles have explicit zero API token prices.

For example:

```json
{"provider": "anthropic", "model": "claude-sonnet-4-6", "prompt": "Summarize this text."}
```

Configured membership does not establish live availability. Candidate selection follows registry order unless a provider is explicitly pinned.

#### Files

`base.py` holds the provider protocol and the normalized result, usage and error types. `registry.py` builds the hosted providers that have keys and the local models from `local_models.yaml`, and picks candidates. `llm.py` is the any-llm adapter: it turns a neutral request into any-llm's call and the reply back into a `ProviderResult`. `content.py` normalizes text, system, image and tool blocks. `prompted_tools.py` is the tool-calling fallback for local models with no native tool API.

Timeouts, retries and the concurrency cap are set in `config/providers.yaml`.

See [orchestration](../orchestration/README.md) for retries, profile verification, budgets, and finalization. Live calls are excluded from the offline test suite; use `POST /api/llm/chat` with an explicit provider/model to probe a configured service, and `POST /api/llm/embed` for embeddings.
