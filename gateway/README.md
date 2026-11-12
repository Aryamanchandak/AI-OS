# AI OS Gateway

For direct calls without running the gateway, use [simple_llm](simple_llm/README.md).
Put keys in that folder’s `.env` and import `LLM`; it has no gateway dependencies.

One local API for ingestion to use OpenAI, Anthropic and local Ollama models.
Provider keys stay in the gateway; callers use `AI_OS_TOKEN`.

## Run

```bash
uv sync --no-editable --extra dev
cp .env.example .env
```

Fill in `.env`: set `AI_OS_TOKEN` and the provider keys you use.
For local models, start Ollama with the models in `config/local_models.yaml`.
Then run:

```bash
.venv/bin/python main.py
```

Address: `http://127.0.0.1:8000`. Call `/health` to check the server.
API calls require `Authorization: Bearer <AI_OS_TOKEN>`.

## Use from ingestion

- `POST /api/llm/chat`: send `prompt` or `messages`, and a `provider`/`model`
  or a named `profile`. Use `response_format` for structured JSON output.
- `POST /api/llm/embed`: send `text` and `profile: chunker-v1` for the pinned
  local 768-dimensional embedding model.
- `POST /api/llm/preflight`: checks chat and embeddings with real model calls.
- `GET /api/llm/providers`: shows configured providers and chat profiles.

Profiles live in `config/profiles.yaml`. Authenticated `/docs` describes request
fields. These are the gateway's own endpoints; an OpenAI SDK needs an adapter
rather than just changing its base URL.

Calls are recorded in `../Database/sqlite/gateway.sqlite`
(override with `GLC_GATEWAY_DB`). A failed ledger write fails the request.

## Checks

```bash
.venv/bin/python -m pytest
.venv/bin/python -m mypy main.py src/gateway
```

Normal tests use fake providers. `pytest -m golden` makes real provider calls;
see [validation status](docs/plans/README.md).
