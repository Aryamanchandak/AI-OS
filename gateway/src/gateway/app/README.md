# Application assembly

This folder turns the gateway's domain services into a running FastAPI application. Start reading at `main.py`, then follow `lifespan.py` to see how its dependencies are created.

## Files

| File | Responsibility |
| --- | --- |
| `main.py` | Defines `create_app()` and the module-level ASGI `app`; registers health checks, service diagnostics, domain routers, API 404 handlers, and optional shell static assets. Redirects `/dashboard` to `/observability`. |
| `lifespan.py` | Builds settings, the service registry, audit and ledger databases, telemetry, the shared HTTP client, and `LLMService`; creates and attaches the semantic cache; runs startup checks and closes owned resources on shutdown. |
| `dependencies.py` | Defines the typed `DependencyContainer` on `app.state.container` and FastAPI dependencies that expose it, the service registry, or the LLM service to routes. |
| `middleware.py` | Implements bearer authentication for `/api/` routes, schema/docs paths, and selected legacy observability paths. A missing configured token returns 503; a mismatched header returns 401. |
| `router_registry.py` | Defines router registrations and installs the LLM and observability routers, including deprecated aliases. |
| `__init__.py` | Marks this as the application-wiring package. |

## Runtime behavior

Startup must complete before the dependency container is available. Named dependency failures are wrapped in `StartupDependencyError`. Shutdown flushes telemetry and closes the shared HTTP client.

Canonical domain APIs live below `/api/llm` and `/api/observability`; LLM aliases also exist below `/v1`. Authentication is path-specific: the middleware does not apply a blanket token requirement to every `/v1` route. Unknown `/api/...` and `/v1/...` paths return 404 before the frontend navigation fallback can handle them.

The frontend is served only when the sibling `shell/dist` exists. Its source is outside this package. Related code: [platform](../platform/README.md), [LLM API](../llm/api/README.md).
