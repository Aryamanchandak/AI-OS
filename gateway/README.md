# AI OS Gateway

The one internal UI-serving FastAPI process. It owns ingestion and the other
migrated domains, mounts their routers, and serves the built React shell.

Gateway owns its Python environment. Set it up once with:

```bash
cd "/Users/aryamanchandak/Documents/AI OS/gateway"
uv sync --no-editable --extra dev
```

```bash
cd "/Users/aryamanchandak/Documents/AI OS/shell"
npm run build

cd "/Users/aryamanchandak/Documents/AI OS/gateway"
AI_OS_TOKEN=local-dev-token AI_OS_PREVIEW=1 \
  .venv/bin/python main.py
```

Open `http://127.0.0.1:8000/ingestion`. The shell asks for the bearer token;
the preview token in the example is `local-dev-token`.

When the preview journey works, remove `AI_OS_PREVIEW=1` from the same command
to use the real ingestion coordinator. The gateway uses the root `Database`
folder by default; `INGESTION_DATABASE_ROOT` can still override it.

Non-secret process defaults live in `config/gateway.yaml`; named service
addresses live in `config/services.yaml`. A service value can be overridden
with `AI_OS_SERVICE_<NAME>_HOST`, `AI_OS_SERVICE_<NAME>_PORT`, or
`AI_OS_SERVICE_<NAME>_ENABLED`. Overrides receive the same validation as YAML,
including duplicate enabled-port rejection. Optional workers are not probed at
startup: if one is unavailable, only its owning feature should degrade. Missing
or invalid required configuration still prevents Gateway from starting.

Port 8000 is the deliberate stable Gateway entry point. `main.py` resolves its
host and port from the validated service registry, including
`AI_OS_SERVICE_GATEWAY_HOST` and `AI_OS_SERVICE_GATEWAY_PORT` overrides. Run one Gateway process for chat, ingestion, and audit.

If an external caller still needs port 8111, stop the standalone GLC server and
start the forwarding listener in a second process:

```bash
cd gateway
.venv/bin/python -m gateway.compatibility.legacy_listener
```

It forwards HTTP (including SSE) and WebSocket traffic to Gateway using the
registry addresses. It logs only timestamp, protocol, and connecting IP; it
does not log paths, queries, headers, or bodies. Keep its logs for the cutover
report if you want usage data. This listener is optional compatibility; Gateway
itself does not require it. Disable `glc_legacy` in the registry when you no
longer want to offer the old port. See `migration/plan-07-cutover-status.md`
for the local verification record.

If you retain the listener's timestamped logs, generate daily counts with
`python scripts/legacy_usage_report.py --start YYYY-MM-DD --end YYYY-MM-DD
listener.log`.

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
`/dashboard` redirects to the shell's `/observability` screen; `/` remains the
ingestion landing page. `/healthz` preserves the old JSON health response.

Gateway owns the migrated GLC audit and ledger domains. Their SQLite files default to
`../Database/sqlite/audit.sqlite` and `gateway.sqlite`; `GLC_AUDIT_DB` and `GLC_GATEWAY_DB`
remain supported overrides. Audit writes are fail-closed.

## Regression commands

Run these commands without any preconfigured environment variables:

```bash
cd "/Users/aryamanchandak/Documents/AI OS/gateway"
.venv/bin/python -m pytest ingestion_tests
.venv/bin/python -m mypy --strict src/gateway/ingestion/server.py
.venv/bin/python -m pytest
.venv/bin/python export_openapi.py
.venv/bin/python -m mypy --config-file mypy.ini main.py src/gateway

cd ../shell
npm run types:generate
npx tsc -b
npx vite build
npx vitest run
```

`pytest` checks both committed generated artifacts for staleness. Vitest uses
its default `passWithNoTests: false`, so a missing UI test suite is a failure.
