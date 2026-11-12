# AI OS Gateway

One local HTTP API for Claude, GPT and local Ollama models. Provider keys stay in
the gateway; callers send `AI_OS_TOKEN`. Every call is priced, checked against a
budget and written to a ledger.

## Run

```bash
uv sync --no-editable --extra dev
```

```bash
cp .env.example .env
```

Fill in `.env`: set `AI_OS_TOKEN` and the provider keys you use. For local models,
start Ollama with the models in `config/local_models.yaml`. Then run:

```bash
.venv/bin/python main.py
```

Address: `http://127.0.0.1:8000`. `/health` needs no token. Every `/api/` call
needs `Authorization: Bearer <AI_OS_TOKEN>`.

## Use

- `POST /api/llm/chat`: send `prompt` or `messages`, and either a named `profile`
  or a `provider` and `model`. Use `response_format` for JSON checked against a schema.
- `POST /api/llm/embed`: send `text` and `profile: chunker-v1` for the pinned
  local 768-dimension embedding model.
- `POST /api/llm/preflight`: makes one real chat call and one real embedding call.
- `GET /api/llm/providers`: shows configured providers and chat profiles.
- `GET /api/llm/calls`, `/cost/by_agent`, `/cost/by_principal`, `/budget`, `/pricing`:
  read the ledger, spend, budgets and prices.

Authenticated `/docs` describes every request field. These are the gateway's own
endpoints; an OpenAI SDK needs an adapter rather than a changed base URL.

Calls are recorded in `../Database/sqlite/gateway.sqlite` (override with
`GLC_GATEWAY_DB`). A failed ledger write fails the request.

## Code

Everything is in `src/gateway/`, one file per job:

| File | Job |
|---|---|
| `app.py` | The FastAPI app: startup, bearer-token auth, every `/api/llm/*` route |
| `service.py` | What a chat or embedding call does, step by step |
| `providers.py` | The only file that talks to model vendors (through any-llm) |
| `content.py` | Helpers that turn message content, images and tool calls into plain values |
| `models.py` | Request and response shapes |
| `profiles.py` | Named provider and model pins from `config/profiles.yaml` |
| `pricing.py` | Cost of a call from `config/pricing.yaml` |
| `budget.py` | Spending limits per agent or session from `config/budgets.yaml` |
| `ledger.py` | The SQLite table with one row per call |
| `db.py` | The only file that opens SQLite |
| `telemetry.py` | The only file that imports OpenTelemetry |
| `config.py` | Paths, `.env` and the YAML loader |

A chat call runs these steps in `service.py`, in order: validate, resolve the
profile, normalise the messages, pick providers, reserve budget, call the
provider, check structured output, then finalise. Finalise always runs; it settles
the budget and writes the ledger row.

`simple_llm/` is a separate one-file client for side projects that call a
provider directly. AI OS code does not import it.

## Checks

```bash
.venv/bin/python -m pytest
```

```bash
.venv/bin/python -m mypy main.py src/gateway
```

Normal tests use fake providers. `pytest -m golden` makes real provider calls and
needs keys in `.env`; it has not yet been run with real keys.

## Docs

- `DECISIONS.md`: why things are the way they are.
- `docs/dependencies.md`: each dependency and what it is for.
- `docs/integrations/graphiti.md`: how Graphiti would call this gateway.
- `docs/history/`: finished step plans and reviews. They describe the old file layout.
