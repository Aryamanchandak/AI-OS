# `web/app.py`

This is the entire web layer of Consequence Radar: a FastAPI application factory (`create_app`), the module-level `app` instance built from it, and the `run()` function that boots it under uvicorn. It exposes two audiences through the same routes' underlying data — a server-rendered HTML UI (`/`, `/runs`, `/runs/{run_id}`) for humans, and a JSON API (`/api/v1/...`) for programmatic access and for the page's own JavaScript. It does not implement any causal-graph or LLM logic itself; it is a thin orchestration/presentation shell around `Pipeline`, `Repository`, and the Pydantic models defined elsewhere in the package.

## Framework and wiring

The framework is **FastAPI** (not Flask), served by **uvicorn**. Templates are Jinja2 via `fastapi.templating.Jinja2Templates`, static files are mounted at `/static` via `StaticFiles`. Imports at the top tie this file to the rest of the package:

- `from ..config import Settings, get_settings` — reads host/port/worker/timeout/API-key configuration (`consequence_radar/config/__init__.py`).
- `from ..models import NewsBatch` — the request body schema for submitting a batch of news URLs (`items: list[NewsItem]`, 1–100 entries, `target_market` fixed to `"indian_equities"`).
- `from ..pipeline import Pipeline` — the actual causal-graph/quantification/report pipeline; `app.py` only ever calls `pipeline_factory().run(run_id)`, it never touches pipeline internals.
- `from ..report import export_markdown` — converts a validated `NewsletterReport` into Markdown for the download endpoint.
- `from ..storage import Repository` — the persistence layer (SQLite-backed, `database_url` from settings) for runs, artifacts, and progress events. All the app's handlers do is call `repo.create_run`, `repo.get_run`, `repo.list_runs`, `repo.artifact(s)`, `repo.events_since`, `repo.set_status`, `repo.add_event`.

`create_app(settings=None, repository=None, pipeline_factory=None)` accepts all three as overridable dependencies (useful for tests — a fake `Repository` or `pipeline_factory` can be injected), defaulting to real config/SQLite/`Pipeline`. It calls `repo.init_schema()` eagerly at app-construction time, and builds a `ThreadPoolExecutor` (`workers`, sized by `settings.worker_count`, default 2, range 1–8) used to run pipeline executions off the async event loop. A `lifespan` context manager shuts the executor down (`cancel_futures=True`) when the app stops; note that in-flight runs are simply cancelled, not gracefully drained, which is why the SSE stream (see below) has to defensively assume a run can get stuck non-terminal forever.

`app.state.repo`, `app.state.settings`, `app.state.workers` are stashed on FastAPI's `app.state` (not otherwise read in this file, but available for tests/extensions).

## The `start()` helper and how runs are launched

```python
def start(run_id: str):
    try: pipeline_factory().run(run_id)
    except Exception as exc:
        repo.set_status(run_id, "failed", error=str(exc)); repo.add_event(run_id, "failed", str(exc), "error")
```

This is a synchronous function submitted to the thread pool (`workers.submit(start, run_id)`) by both run-creation routes. It is the sole place that invokes the pipeline. Any exception raised by `Pipeline.run` — including presumably exceptions the pipeline itself doesn't already catch — is turned into a `failed` run status and an error event, so a route caller never sees pipeline exceptions directly; they only ever see the run transition to a terminal status the UI/API can poll or stream.

## Routes

### `GET /` → `index()`
Renders `index.html` via the `index_response()` helper, which supplies `runs` (from `repo.list_runs()`), `has_key` (`bool(settings.api_key)` — true if either `GEMINI_API_KEY` or `GOOGLE_API_KEY` is set), and empty `form_error`/`form_value`. This is the landing page and run-history list. (`index_response` passes `request` to `TemplateResponse` positionally; `run_page`, below, passes it both positionally *and* again inside its context dict — harmless but inconsistent, likely leftover from migrating off an older Starlette `TemplateResponse` call convention.)

### `POST /runs` → `create_run_from_form()`
A classic HTML form submission (`Form(...)` field `news`, a textarea of newline-separated URLs), explicitly documented in the code as "Progressive-enhancement fallback when the browser script cannot run" — i.e. this exists so the site works with JavaScript disabled, mirroring what `app.js` does via fetch for the JS-enabled path. The route is declared `response_class=HTMLResponse`, but its success path actually returns a `RedirectResponse` (303) — the declared response class only describes the validation-failure branch; FastAPI doesn't enforce it against what a handler actually returns, so this is a minor decoration mismatch rather than a bug. It splits `news` into stripped non-empty lines, builds a `NewsBatch(items=[{"url": url} for url in lines])`, and:
- On validation failure (`ValueError` from Pydantic, e.g. 0 or >100 URLs, malformed URLs) it re-renders `index.html` with a 422 status and a fixed error string ("Enter 1–100 complete http:// or https:// article URLs, one per line.") plus `form_value=news` so the user's input isn't lost.
- On success it calls `repo.create_run(batch)`, submits `start(run_id)` to the thread pool, and issues a `303 See Other` redirect to `/runs/{run_id}`.

### `GET /runs/{run_id}` → `run_page()`
Looks up the run (`repo.get_run(run_id)`; 404 if missing) and renders `run.html` with a large context dict: `run`, `report` (falls back from the validated `"report"` artifact to `"report_draft"` if validation hasn't produced a final one), `validation` (`"report_validation"` artifact), `candidates` (defaults to `[]`), `graph`, `cases`, `audit` (all artifacts via `repo.artifacts(run_id)`), `events` (`repo.events_since(run_id)`, i.e. full history from sequence 0), and `usage`. This one route serves three very different visual states in `run.html` — in-progress, failed, and completed — chosen entirely by `run.status` inside the template (see the `run.html` doc).

### `POST /api/v1/runs` → `create_run()` (status 202)
The JSON counterpart to the form route, and what `app.js` actually calls. Body is parsed directly as a `NewsBatch` (FastAPI does the Pydantic validation and returns FastAPI's standard 422 error shape on failure — `app.js` reads `data.detail?.[0]?.msg` expecting this). On success: `repo.create_run(batch)`, `workers.submit(start, run_id)`, and returns `{"run_id": ..., "status": "queued", "url": f"/runs/{run_id}"}`. The client is expected to navigate to `url`.

### `GET /api/v1/runs/{run_id}` → `run_status()`
Returns the raw `repo.get_run(run_id)` dict as JSON, or 404. Simple polling-style status endpoint (though the app itself prefers the SSE stream below over polling this).

### `GET /api/v1/runs/{run_id}/events` → `events()`
A Server-Sent Events (SSE) stream, `text/event-stream`, consumed by `app.js`'s `EventSource`. This is the most intricate handler in the file:
- Accepts an `after` query param (default 0) as the starting event-sequence cursor, but also honors the standard SSE `Last-Event-ID` header on reconnect, taking `max(after, int(last-event-id))` — the code comment explains this exists because early versions ignored the resend and re-appended the whole event history to the DOM list on every browser reconnect.
- The inner `stream()` generator polls `repo.events_since(run_id, cursor)` every 0.35s, yielding SSE-formatted `id: N\ndata: {...json...}\n\n` lines, advancing `cursor` to each event's `sequence`.
- It computes a `deadline` of `settings.max_wall_time_seconds + 60` from the moment the connection starts (not from run start), specifically to stop polling SQLite forever for a run whose worker thread was killed by executor shutdown and therefore never reaches a `TERMINAL` status (`{"completed", "completed_with_warnings", "failed", "report_validation_failed"}`).
- On detecting a terminal run status it does one more `await asyncio.sleep(0.35)` and a final drain before returning — the comment explains this closes a race where the pipeline flips the DB status to terminal *before* writing its last event row, so an immediate return could drop the final line and strand the browser on the in-progress view until a reload.
- It deliberately does **not** call `request.is_disconnected()` itself, noting that Starlette already cancels the generator on client disconnect and calling it manually would race Starlette's own listener on the same receive channel.
- Response headers disable caching and disable nginx's proxy buffering (`X-Accel-Buffering: no`) so events actually stream rather than batching up.

### `GET /api/v1/runs/{run_id}/report` → `report()`
Query param `format` (default `"json"`). Reads the `"report"` artifact (only the *validated* report — not the draft fallback used by `run_page`); 404 if absent. `format=markdown` converts it via `NewsletterReport.model_validate(data)` and `export_markdown(...)`, returned as `PlainTextResponse` with a `Content-Disposition: attachment` header prompting a file download named `consequence-radar-{run_id}.md`. Any other/default `format` value just returns the raw stored JSON dict (FastAPI JSON-encodes it automatically) — there's no validation that `format` is one of a known set; an unrecognized value silently falls through to the JSON branch rather than erroring.

### `GET /api/v1/runs/{run_id}/graph` → `graph()`
Returns the `"graph"` artifact JSON, 404 if not present.

### `GET /api/v1/runs/{run_id}/audit` → `audit()`
404s if the run doesn't exist at all; otherwise returns `{"run": ..., "artifacts": repo.artifacts(run_id), "events": repo.events_since(run_id)}` — the full artifact history (not just latest per kind) plus the complete event log. This is the endpoint linked from `run.html`'s failure state ("Inspect the retained audit JSON").

### `GET /api/v1/runs/{run_id}/export` → `export()`
Fetches the run with `include_artifacts=True`, adds `run["events"] = repo.events_since(run_id)`, and returns it as a `JSONResponse` with a `Content-Disposition: attachment` header forcing a download (`consequence-radar-{run_id}.json`). This is a superset of `/audit` shaped for the "Download run JSON" link in the completed-report view.

### `GET /health` → `health()`
Returns `{"status": "ok", "database": "ok", "live_credentials_configured": bool(settings.api_key)}`. Note this is not a real database health check — `"database": "ok"` is a hardcoded literal, not the result of actually pinging `repo`/SQLite. A broken DB connection would not be caught here; it would only surface as a 500 or 404 mismatch on the actual data routes.

## Module-level `app` and `run()`

```python
app = create_app()

def run():
    import uvicorn
    settings = get_settings()
    uvicorn.run("consequence_radar.web.app:app", host=settings.web_host, port=settings.web_port, reload=False)
```

`app` is built eagerly at import time with default settings/repository/pipeline — this is what uvicorn's string-based app reference (`"consequence_radar.web.app:app"`) resolves to, and it's also what a plain `uvicorn consequence_radar.web.app:app` CLI invocation would find. `run()` is imported and called by `src/consequence_radar/__main__.py` (`from .web.app import run; run()` under `if __name__ == "__main__"`), so `python -m consequence_radar` starts the server this way.

Host/port come from `Settings`: `web_host` defaults to `"127.0.0.1"` (loopback only — not exposed externally by default) and `web_port` defaults to `8010` (constrained 1024–65535 by the `Settings` field). `reload=False` is hardcoded — there is no dev/hot-reload mode wired through `run()`; a developer wanting autoreload would have to bypass `run()` and invoke uvicorn directly with `--reload`. There's also no `workers=` or TLS configuration here — this is a single-process, plain-HTTP entry point, presumably meant to sit behind a reverse proxy in any real deployment (consistent with the SSE handler's nginx-buffering header).

## Connections to neighboring files

- **`app.js`** calls `POST /api/v1/runs` (JSON, matches `create_run`) and opens `EventSource` on `/api/v1/runs/{id}/events` (matches `events()`), using `window.RADAR_RUN_ID`/`window.RADAR_RUNNING` globals that `run.html` embeds into a `<script>` block server-side.
- **`index.html`** is rendered only by `index()` and `create_run_from_form()` (the latter on both success-redirect-away and validation-failure-rerender paths); it posts synchronously to `/runs` (plain form) while `app.js` intercepts that same form and posts to `/api/v1/runs` instead, so the `<form action="/runs" method="post">` in `index.html` is a true no-JS fallback path, not dead markup.
- **`run.html`** is rendered only by `run_page()`, and its three branches (`in progress` / `failed` / everything else) are driven directly by the `run.status` value that `Repository` persists — this file has no independent notion of pipeline stages beyond the `TERMINAL` set and whatever status strings `Pipeline`/`Repository` produce.
- **`styles.css` / fonts** are served through the `/static` mount from both templates.
- Downstream of `app.py`, `Pipeline.run(run_id)` (in `consequence_radar/pipeline/`) is a black box from this file's perspective — `app.py` only knows it must be called on a worker thread, may raise, and is expected to write status/events/artifacts into the same `Repository` this file also reads from.
