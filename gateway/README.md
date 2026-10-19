# AI OS Gateway

The single entry point for all LLM calls. One FastAPI process that owns the
LLM, audit and ledger domains, mounts their routers, and serves the built React
shell.

Gateway owns its Python environment. Set it up once with:

```bash
cd "/Users/aryamanchandak/Documents/AI OS/gateway"
uv sync --no-editable --extra dev
```

```bash
cd "/Users/aryamanchandak/Documents/AI OS/shell"
npm run build

cd "/Users/aryamanchandak/Documents/AI OS/gateway"
AI_OS_TOKEN=local-dev-token .venv/bin/python main.py
```

Open `http://127.0.0.1:8000/`. The shell asks for the bearer token; the token
in the example is `local-dev-token`.

Named service addresses and the Gateway bind address live in `config/services.yaml`. A service value can be overridden
with `AI_OS_SERVICE_<NAME>_HOST`, `AI_OS_SERVICE_<NAME>_PORT`, or
`AI_OS_SERVICE_<NAME>_ENABLED`. Overrides receive the same validation as YAML,
including duplicate enabled-port rejection. Optional workers are not probed at
startup: if one is unavailable, only its owning feature should degrade. Missing
or invalid required configuration still prevents Gateway from starting.

Port 8000 is the deliberate stable Gateway entry point. `main.py` resolves its
host and port from the validated service registry, including
`AI_OS_SERVICE_GATEWAY_HOST` and `AI_OS_SERVICE_GATEWAY_PORT` overrides. Run one Gateway process for chat and audit.

Authenticated service diagnostics are available at
`/api/diagnostics/services`. The response is an allow-listed address view and
never includes environment secrets.

## Restored operational contracts

- `POST /api/llm/preflight` (legacy alias `/v1/preflight`) probes chat and
  embeddings concurrently through the LLM service. Each probe has a 30-second
  deadline. The response reports each probe's result with redacted errors;
  model probes still use the normal budget and audit path.
- `/api/observability/traces/recent`, `/traces/{trace_id}`, `/refusals`, and
  `/agent_trace/{run_id}` restore the observability reads. Their legacy aliases
  are `/v1/traces/recent`, `/v1/traces/{trace_id}`, `/v1/refusals`, and
  `/v1/observability/agent_trace/{run_id}`. All observability reads require
  `AI_OS_TOKEN`, including the legacy URLs.

The trace store retains at most 50 traces with 200 spans each. Refusal storage
retains the last 100 HTTP 402 events and a total count. Both reset on restart.
Request and LLM-stage traces exclude prompts, completions, request headers,
queries, and exception bodies. Successful chat responses include their trace
and span IDs. Refusal details retain only redacted budget fields.

The agent-trace proxy uses only the enabled `agent_runtime` registry entry;
an arbitrary `base_url` override is rejected. An absent, disabled, or
unreachable runtime returns 503. Invalid upstream trace data returns 502.
`/dashboard` redirects to the shell's `/observability` screen. `/healthz`
preserves the old JSON health response.

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
