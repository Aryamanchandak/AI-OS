# AI OS Gateway

The one internal UI-serving FastAPI process. It mounts domain routers and
serves the built React shell; domain logic remains in its owning project.

Gateway owns its Python environment. Set it up once with:

```bash
cd "/Users/aryamanchandak/Documents/AI OS/gateway"
uv sync --extra dev
```

```bash
cd "/Users/aryamanchandak/Documents/AI OS/shell"
npm run build

cd "/Users/aryamanchandak/Documents/AI OS/gateway"
AI_OS_TOKEN=local-dev-token AI_OS_PREVIEW=1 \
  .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
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

Authenticated service diagnostics are available at
`/api/diagnostics/services`. The response is an allow-listed address view and
never includes environment secrets.

Gateway now owns the migrated GLC policy, security, audit, ledger, and control
domains. Their SQLite files default to `../Database/sqlite/audit.sqlite`,
`gateway.sqlite`, and `pairings.sqlite`; `GLC_AUDIT_DB`, `GLC_GATEWAY_DB`, and
`GLC_PAIRING_DB` remain supported overrides. Audit writes are fail-closed.

The compatibility control routes remain at `/v1/control/*` and use the GLC
install token, not `AI_OS_TOKEN`. Policy reload is available at
`POST /v1/control/reload-policy` and through SIGHUP; both call the same atomic
reload operation and are audited. In the unified process, `/v1/control/kill`
suspends the GLC capability but deliberately does not terminate Gateway,
ingestion, or the shell.

## Regression commands

Run these commands without any preconfigured environment variables:

```bash
cd "/Users/aryamanchandak/Documents/AI OS/ingestion-pipeline/merged-ingestion"
./.venv/bin/python -m pytest
./.venv/bin/python -m mypy --strict cockpit/server.py

cd "/Users/aryamanchandak/Documents/AI OS/gateway"
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
