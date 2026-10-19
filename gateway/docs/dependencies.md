# Gateway dependencies

Every library the gateway installs. Versions are the exact pins in `uv.lock`;
`pyproject.toml` holds the allowed ranges. Update this file in the same commit
as any dependency change.

Last checked: 2026-10-19.

## Runtime

| Library | Version | Job | Why chosen | Exit plan |
| --- | --- | --- | --- | --- |
| fastapi | 0.141.1 | Web framework: routes, request validation, OpenAPI schema | Standard for typed Python APIs; generates the `contracts/openapi.json` the shell builds its types from | Starlette or Litestar; routes and dependency wiring would need rewriting |
| uvicorn | 0.53.0 | Runs the FastAPI app as a server (`main.py` only) | Default server for FastAPI | Hypercorn or Granian; one-line change in `main.py` |
| any-llm-sdk[anthropic,ollama,openai] | 1.29.0 | Calls Claude, GPT and Ollama (chat and embeddings) and translates each vendor's format to one shape | Mozilla's maintained wrapper over the official vendor SDKs; replaced ~1,000 hand-written lines | Only `src/gateway/llm/providers/llm.py` imports it; swap for LiteLLM or the vendor SDKs behind the same file |
| tenacity | 9.1.4 | Retries a provider call after a timeout, 429 or 5xx, with backoff | Standard retry library; keeps the retry count the gateway reports | Only `src/gateway/llm/orchestration/provider_call.py` imports it; vendor SDKs have their own retries as a fallback |
| httpx | 0.28.1 | Test-only now: FastAPI's test client and the fake transports in `tests/test_llm_adapter.py` | Installed anyway by FastAPI's test client and the vendor SDKs | Leaves when nothing imports it |
| pydantic | 2.13.5 | Typed request/response models and config validation | Built into FastAPI; validates config at startup | Required by FastAPI; leaves only if FastAPI leaves |
| pyyaml | 6.0.3 | Reads the YAML files in `config/` | Standard YAML parser | ruamel.yaml; a near drop-in replacement |
| jsonschema | 4.26.0 | Checks that LLM "structured output" replies match the requested JSON shape | Reference implementation of the JSON Schema standard | fastjsonschema; only `llm/orchestration/structured_output.py` uses it |
| opentelemetry-api | 1.44.0 | Tracing calls inside the code (spans) | Vendor-neutral tracing standard | Remove tracing; touches 4 files |
| opentelemetry-sdk | 1.44.0 | Collects and processes the spans | Pairs with the API above | Same as above |
| opentelemetry-exporter-otlp-proto-http | 1.44.0 | Sends spans to an external tracing backend over HTTP | Works with any OTLP backend (Jaeger, Honeycomb, etc.) | Drop it if traces are never exported off-machine |
| python-dotenv | 1.2.3 | Loads API keys and `AI_OS_TOKEN` from `gateway/.env` at app creation | Standard `.env` reader; shell variables still win | Only `src/gateway/env.py` imports it; replace with a 10-line parser or plain shell exports |

## Development only (`uv sync --extra dev`)

| Library | Version | Job | Why chosen | Exit plan |
| --- | --- | --- | --- | --- |
| pytest | 9.1.1 | Runs the test suite | Standard Python test runner | None needed |
| mypy | 2.3.1 | Strict type checking (`[tool.mypy]` in `pyproject.toml`) | Reference Python type checker | pyright |

## Build only

| Library | Version | Job | Why chosen | Exit plan |
| --- | --- | --- | --- | --- |
| setuptools | ≥68 (not locked) | Builds the `gateway` package from `src/` | Python default build backend | hatchling; change `[build-system]` in `pyproject.toml` |

## Known gap

CLAUDE.md asks for each library to sit behind one thin adapter file. FastAPI is
imported directly in many files; it is the framework itself, so an adapter is impractical.
