# AI OS Gateway

The one internal UI-serving FastAPI process. It mounts domain routers and
serves the built React shell; domain logic remains in its owning project.

```bash
cd "/Users/aryamanchandak/Documents/AI Code/AI OS/shell"
npm run build

cd ../gateway
AI_OS_TOKEN=local-dev-token AI_OS_PREVIEW=1 \
  "/Users/aryamanchandak/Documents/AI Code/ingestion-pipeline/merged-ingestion/.venv/bin/python" \
  -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/ingestion`. The shell asks for the bearer token;
the preview token in the example is `local-dev-token`.

## Regression commands

Run these commands without any preconfigured environment variables:

```bash
cd "/Users/aryamanchandak/Documents/AI Code/ingestion-pipeline/merged-ingestion"
./.venv/bin/python -m pytest
./.venv/bin/python -m mypy --strict cockpit/server.py

cd "/Users/aryamanchandak/Documents/AI Code/AI OS/gateway"
"/Users/aryamanchandak/Documents/AI Code/ingestion-pipeline/merged-ingestion/.venv/bin/python" -m pytest
"/Users/aryamanchandak/Documents/AI Code/ingestion-pipeline/merged-ingestion/.venv/bin/python" export_openapi.py
"/Users/aryamanchandak/Documents/AI Code/ingestion-pipeline/merged-ingestion/.venv/bin/python" -m mypy --config-file mypy.ini main.py

cd ../shell
npm run types:generate
npx tsc -b
npx vite build
npx vitest run
```

`pytest` checks both committed generated artifacts for staleness. Vitest uses
its default `passWithNoTests: false`, so a missing UI test suite is a failure.
