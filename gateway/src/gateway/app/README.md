# Application assembly

This folder turns the gateway's domain services into a running FastAPI application. Start reading at `main.py`, then follow `lifespan.py` to see how its dependencies are created.

## Files

| File | Responsibility |
| --- | --- |
| `main.py` | Defines `create_app()` and the module-level ASGI `app`; registers `/health`, the domain routers, and the `/api/...` 404 handler. |
| `lifespan.py` | Builds the audit and ledger databases, telemetry, the shared HTTP client, and `LLMService`; runs startup checks and closes owned resources on shutdown. |
| `dependencies.py` | Defines the typed `DependencyContainer` on `app.state.container` and FastAPI dependencies that expose it or the LLM service to routes. |
| `middleware.py` | Implements bearer authentication for `/api/` routes and schema/docs paths. A missing configured token returns 503; a mismatched header returns 401. |
| `router_registry.py` | Defines router registrations and installs the LLM and observability routers. |
| `__init__.py` | Marks this as the application-wiring package. |

## Runtime behavior

Startup must complete before the dependency container is available. Named dependency failures are wrapped in `StartupDependencyError`. Shutdown flushes telemetry and closes the shared HTTP client.

Domain APIs live below `/api/llm` and `/api/observability`. Unknown `/api/...` paths return a JSON 404. Related code: [platform](../platform/README.md), [LLM API](../llm/api/README.md).
