# Gateway dependencies

Every library the gateway installs. Versions are the exact pins in `uv.lock`;
`pyproject.toml` holds the allowed ranges. Update this file in the same commit
as any dependency change.

Last checked: 2026-10-17.

## Runtime

| Library | Version | Job | Why chosen | Exit plan |
| --- | --- | --- | --- | --- |
| fastapi | 0.141.1 | Web framework: routes, request validation, OpenAPI schema | Standard for typed Python APIs; generates the `contracts/openapi.json` the shell builds its types from | Starlette or Litestar; routes and dependency wiring would need rewriting |
| uvicorn | 0.53.0 | Runs the FastAPI app as a server (`main.py` only) | Default server for FastAPI | Hypercorn or Granian; one-line change in `main.py` |
| httpx | 0.28.1 | Outbound HTTP calls to LLM providers (sync, async, streaming) | Async plus streaming support; FastAPI's test client uses it too | aiohttp; provider adapters would need rewriting |
| pydantic | 2.13.5 | Typed request/response models and config validation | Built into FastAPI; validates config at startup | Required by FastAPI; leaves only if FastAPI leaves |
| pyyaml | 6.0.3 | Reads the YAML files in `config/` | Standard YAML parser | ruamel.yaml; a near drop-in replacement |
| jsonschema | 4.26.0 | Checks that LLM "structured output" replies match the requested JSON shape | Reference implementation of the JSON Schema standard | fastjsonschema; only `llm/orchestration/structured_output.py` uses it |
| opentelemetry-api | 1.44.0 | Tracing calls inside the code (spans) | Vendor-neutral tracing standard | Remove tracing; touches 4 files |
| opentelemetry-sdk | 1.44.0 | Collects and processes the spans | Pairs with the API above | Same as above |
| opentelemetry-exporter-otlp-proto-http | 1.44.0 | Sends spans to an external tracing backend over HTTP | Works with any OTLP backend (Jaeger, Honeycomb, etc.) | Drop it if traces are never exported off-machine |
| python-dotenv | 1.2.3 | Meant to load `.env` files | — | **Unused: nothing imports it.** API keys currently come only from the process environment. Either remove it, or add a thin loader so keys come from `.env` as CLAUDE.md requires. |

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

CLAUDE.md asks for each library to sit behind one thin adapter file. FastAPI,
httpx and PyYAML are imported directly in many files (16, 12 and 8). FastAPI is
the framework itself, so an adapter is impractical for it; httpx and PyYAML
could be wrapped later.
