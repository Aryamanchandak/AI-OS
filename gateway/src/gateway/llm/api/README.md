# LLM HTTP endpoints

This folder translates HTTP requests into `LLMService` calls. `routes.py` defines the router; `preflight.py` implements bounded probes; `__init__.py` exports the registration.

The router is mounted at `/api/llm`.

| Relative endpoint | What it does |
| --- | --- |
| `POST /chat` | Returns completed chat JSON. Requests with `stream: true` receive HTTP 422. |
| `POST /embed` | Requests an embedding through the service. |
| `POST /preflight` | Runs a small chat request and embedding request concurrently, each with a 30-second timeout; returns separate outcomes and redacted errors. |
| `GET /providers`, `/capabilities`, `/embedders`, `/status`, `/chat/profiles/{profile}` | Returns configured provider/profile/capability information and usage summaries. |
| `GET /calls`, `/cost/by_agent`, `/cost/by_principal` | Reads recent calls or attribution rollups from the process-local meter. |
| `GET /budget`, `GET /budget/{principal}`, `POST /budget`, `DELETE /budget/{principal}` | Inspects budget policies/status and changes SQLite-backed runtime overrides. |
| `GET /pricing` | Reports configured prices. |

`_chat_trace()` adds active trace identifiers and selected accounting/provider span attributes to normal chat responses.

Preflight makes real service calls, so it can consume provider resources, create audit records, and encounter budget refusals. Provider/status endpoints mostly report configuration; they do not test every provider. Image requests require a vision-capable provider or profile and embedded image data, such as a base64 `data:` URL. Image links return HTTP 400. Use `image-transcription-v1` for local transcription. Authentication rules are owned by [application middleware](../../app/README.md).
