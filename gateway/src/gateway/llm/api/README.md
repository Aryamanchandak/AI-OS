# LLM HTTP endpoints

This folder translates HTTP requests into `LLMService` calls. `routes.py` defines the router; `preflight.py` implements bounded probes; `__init__.py` exports canonical and alias registrations.

The same router is mounted at `/api/llm` and, as a deprecated compatibility alias, `/v1`.

| Relative endpoint | What it does |
| --- | --- |
| `POST /chat` | Returns normal chat JSON, streaming SSE, or cached JSON when a streaming request hits the semantic cache. |
| `POST /chat/batch` | Runs chat calls with bounded concurrency and returns results in input order, including per-call errors. |
| `POST /vision` | Wraps one image and prompt into a normal chat request, with an optional JSON schema. |
| `POST /embed` | Requests an embedding through the service. |
| `POST /preflight` | Runs a small chat request and embedding request concurrently, each with a 30-second timeout; returns separate outcomes and redacted errors. |
| `GET /providers`, `/capabilities`, `/embedders`, `/status`, `/chat/profiles/{profile}` | Returns configured provider/profile/capability information and usage summaries. |
| `GET /calls`, `/cost/by_agent`, `/cost/by_principal` | Reads recent calls or attribution rollups from the process-local meter. |
| `GET /budget`, `GET /budget/{principal}`, `POST /budget`, `DELETE /budget/{principal}` | Inspects budget policies/status and changes SQLite-backed runtime overrides. |
| `GET /cache/stats`, `POST /cache/purge` | Reports persistent semantic-cache statistics or removes cached entries. |
| `GET /pricing`, `/telemetry`, `/routers` | Reports configured prices and compatibility/status information. The router response is currently empty compatibility data. |

`_chat_trace()` adds active trace identifiers and selected accounting/provider span attributes to normal chat responses. Streaming frames are produced in [orchestration](../orchestration/README.md).

Preflight makes real service calls, so it can consume provider resources, create audit records, and encounter budget refusals. Provider/status endpoints mostly report configuration; they do not test every provider. The vision wrapper does not independently filter candidates by vision capability. Authentication rules are owned by [application middleware](../../app/README.md).
