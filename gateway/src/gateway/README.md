# Gateway source guide

This package runs the AI OS Gateway: a FastAPI application that exposes a common HTTP interface for LLM chat, embeddings, provider diagnostics, budgets, and observability.

`__init__.py` defines the package version. The ASGI entry point is `gateway.app.main:app`; `create_app()` constructs an application with configurable startup paths.

## Folder map

| Folder | What its code does |
| --- | --- |
| [app](app/README.md) | Assembles HTTP routes, authentication, dependency injection, startup, and shutdown. |
| [llm](llm/README.md) | Implements the common chat and embedding service and its request models. |
| [platform](platform/README.md) | Supplies configuration, SQLite helpers, outbound HTTP, service addresses, and tracing. |
| [ledger](ledger/README.md) | The one SQLite record of every LLM call. |

## How a request moves through the code

1. `app/main.py` creates the application. Its lifespan loads configuration and constructs the long-lived services before requests are served.
2. HTTP middleware applies the configured bearer-token policy and captures diagnostic spans for LLM routes.
3. `llm/api/routes.py` translates a request into a call to `LLMService`.
4. Chat passes through validation, profile resolution, input normalization, provider selection, budget reservation, provider execution, and structured-output validation.
5. Finalization reconciles budget reservations and writes one call-ledger row.
6. Embeddings use a separate path in `LLMService`, with profile checks and provider fallback, and also write one ledger row.

The current routing implementation selects from a deterministic provider order; legacy fields for tier classification and escalation do not implement those features here.

Each source folder has its own README. Generated `__pycache__` directories contain interpreter artifacts and are excluded from this documentation.
