# `web/templates/index.html`

The landing page: a hero/pitch section, the "start a research run" form, and a list of past runs. Rendered exclusively by two handlers in `app.py` — `index()` for `GET /` and `create_run_from_form()` for `POST /runs` (on validation failure, or implicitly bypassed via redirect on success) — both going through the shared `index_response()` helper.

## Template variables expected

From `index_response(request, form_error="", form_value="", status_code=200)`:
- `runs` — result of `repo.list_runs()`, a list of run dicts. Each is expected to have `id`, `status`, `created_at` (ISO datetime string), and `batch.items` (a list, whose length is computed inline with `run["batch"]["items"]|length`).
- `has_key` — `bool(settings.api_key)`; when falsy, the form shows a `.notice` warning that live credentials aren't configured and a real run will fail.
- `form_error` — empty string normally; set to a fixed validation message by `create_run_from_form` on bad input (0/>100 or malformed URLs). Rendered into `#form-status` and toggles the `is-error` class via `{% if form_error %} is-error{% endif %}`.
- `form_value` — the raw, unmodified textarea content the user submitted, so it survives a validation-failure re-render (`{{ form_value or '' }}` inside the `<textarea>`).

## Structure and behavior

- `<form id="batch-form" action="/runs" method="post">` — a real HTML form that posts to the `/runs` route (`create_run_from_form` in `app.py`) as a no-JS fallback. `app.js` intercepts this same form's submit event and, when JS is available, posts JSON to `/api/v1/runs` instead and client-redirects — so the `action`/`method` attributes here are only exercised when JavaScript fails to load or run.
- The `#news` textarea (`name="news"`, `required`) is the field FastAPI reads via `Form(...)` in `create_run_from_form`; one URL per line, 1–100 lines expected.
- `#form-status` (`role="status" aria-live="polite"`) is where both the server-rendered `form_error` and the client-side (`app.js`) validation/network-error messages surface — the same element serves both code paths.
- The run history section iterates `runs`, each rendered as an `<a class="run-row" href="/runs/{{ run.id }}">` (linking into `run_page()` in `app.py`) showing a `status status-{{ run.status }}` badge (the CSS in `styles.css` has explicit color rules for `status-completed`, `status-completed_with_warnings`, `status-failed`, `status-report_validation_failed`), an item count, and a truncated timestamp (`run.created_at[:16]|replace('T',' · ')`). A Jinja `{% else %}` on the `{% for %}` renders an empty-state message when there are no runs yet.
- Loads `styles.css` and `app.js` (with `?v=2` cache-bust) via `url_for('static', path=...)`, which resolves through the `StaticFiles` mount at `/static` in `app.py`.

There is no client-side templating beyond Jinja2's server-side rendering — all dynamic content here is baked in at response time, not fetched via JS (the run-history list, notably, is not updated live; a new run only appears after a full page reload/navigation).
