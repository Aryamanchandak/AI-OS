# AI OS Gateway

The single entry point for all LLM calls. One FastAPI process that owns the
LLM, audit and ledger domains, mounts their routers, and has no UI.

Gateway owns its Python environment. Set it up once with:

```bash
cd "/Users/aryamanchandak/Documents/AI OS/gateway"
uv sync --no-editable --extra dev
```

```bash
cd "/Users/aryamanchandak/Documents/AI OS/gateway"
AI_OS_TOKEN=local-dev-token .venv/bin/python main.py
```

The Gateway listens on `127.0.0.1:8000`. `/health` needs no token; every
`/api/...` route requires `Authorization: Bearer $AI_OS_TOKEN`.

## Restored operational contracts

- `POST /api/llm/preflight` probes chat and
  embeddings concurrently through the LLM service. Each probe has a 30-second
  deadline. The response reports each probe's result with redacted errors;
  model probes still use the normal budget and audit path.
- `/api/observability/traces/recent`, `/traces/{trace_id}` and `/refusals`
  restore the observability reads. All of them require `AI_OS_TOKEN`.

The trace store retains at most 50 traces with 200 spans each. Refusal storage
retains the last 100 HTTP 402 events and a total count. Both reset on restart.
Request and LLM-stage traces exclude prompts, completions, request headers,
queries, and exception bodies. Successful chat responses include their trace
and span IDs. Refusal details retain only redacted budget fields.

Gateway owns the migrated GLC audit and ledger domains. Their SQLite files default to
`../Database/sqlite/audit.sqlite` and `gateway.sqlite`; `GLC_AUDIT_DB` and `GLC_GATEWAY_DB`
remain supported overrides. Audit writes are fail-closed.

## Regression commands

Run these commands without any preconfigured environment variables:

```bash
cd "/Users/aryamanchandak/Documents/AI OS/gateway"
.venv/bin/python -m pytest
.venv/bin/python scripts/export_openapi.py
.venv/bin/python -m mypy main.py src/gateway
```

`pytest` checks that the committed `contracts/openapi.json` is current. Tests never read
files outside `gateway/`; keeping the shell's generated TypeScript types in
sync with `contracts/openapi.json` is the shell's job (`npm run types:generate` there).

Dependency documentation lives in [docs/dependencies.md](docs/dependencies.md).
Graphiti integration requirements live in
[docs/integrations/graphiti.md](docs/integrations/graphiti.md).

## Later

Real provider batch processing can return as a separate feature when needed,
with actual asynchronous submission and billing matched to the provider's batch API.
