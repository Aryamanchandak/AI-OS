# `web/static/app.js`

Vanilla client-side JS, no build step or framework, loaded by both `index.html` and `run.html` (`<script src="{{ url_for('static', path='app.js') }}?v=2" defer>` — the `?v=2` query string is a manual cache-buster, bumped by hand whenever the file changes). It has three independent, unguarded behaviors that run on every page load; each checks for the DOM elements/globals it needs before acting, so it's safe to include on pages that don't have them.

## 1. Progressive-enhancement form submit (`index.html` only)

```js
const form = document.querySelector('#batch-form');
if (form) form.addEventListener('submit', async (event) => { ... });
```

`#batch-form` and its `#news` textarea / `#form-status` paragraph only exist in `index.html`; on `run.html` this block is a no-op. On submit it:
1. `preventDefault()`s the native form post (which would otherwise hit `POST /runs`, the server-rendered fallback in `app.py`).
2. Splits the textarea value on newlines, trims, and drops blanks.
3. Client-side validates each line as a URL via the `URL` constructor, rejecting anything that doesn't parse or whose `protocol` isn't `http:`/`https:`, and rejects the whole batch if there are 0 or more than 100 URLs — this mirrors (but does not replace) the same 1–100 / http(s)-only rule enforced server-side by `NewsBatch` in `app.py`'s `create_run_from_form`.
4. On invalid input, sets `#form-status` text to the same message string used server-side ("Enter 1–100 complete http:// or https:// article URLs, one per line.") and adds the `.is-error` CSS class, then returns without submitting anything.
5. On valid input, disables the submit button (`aria-busy="true"`) and does `fetch('/api/v1/runs', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({items: urls.map(url => ({url}))})})` — this is the **JSON API route** `create_run()` in `app.py`, not the `/runs` form route.
6. On a non-OK response, it tries to pull a message out of FastAPI's validation error shape (`data.detail?.[0]?.msg`) or a plain `data.detail` string, falling back to a generic message; on success it does `window.location.assign(data.url)`, where `data.url` is the `/runs/{run_id}` path returned by `create_run()` — this is what actually navigates the browser to the progress page.
7. On any thrown error (including `fetch` network failure) it re-enables the button and shows the error text in `#form-status` with `.is-error`.

## 2. Copy-to-clipboard buttons (both pages)

```js
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
  await navigator.clipboard.writeText(button.dataset.copy); button.textContent='Copied';
}));
```

Any element with a `data-copy` attribute gets a click handler that copies that attribute's value to the clipboard and permanently relabels the button text to "Copied" (it never reverts). `run.html` uses this for its "Copy report Markdown" button, whose `data-copy` holds the full `report.article_markdown` text. There's no error handling if `navigator.clipboard` is unavailable (e.g. insecure context) — the promise rejection is unhandled and the button silently never updates.

## 3. Live progress stream (`run.html` only, while a run is in progress)

```js
if (window.RADAR_RUNNING) {
  const stream = new EventSource(`/api/v1/runs/${window.RADAR_RUN_ID}/events`);
  const list = document.querySelector('#events');
  stream.onmessage = event => { ... };
}
```

`window.RADAR_RUNNING` and `window.RADAR_RUN_ID` are globals that `run.html` sets inline (`<script>window.RADAR_RUN_ID={{ run.id|tojson }};window.RADAR_RUNNING=true;</script>`) only in its "in progress" branch. When present, this opens an `EventSource` against `GET /api/v1/runs/{run_id}/events` — exactly the SSE handler documented in `app.py`. Each incoming message is parsed as JSON and appended as a new `<li>` to `#events` (an `<ol>` that `run.html` seeds with any already-persisted events). If the event's `kind` is `"complete"` or `"error"`, the stream is closed and the page reloads after 350ms (`setTimeout(() => location.reload(), 350)`) so the server can re-render `run.html` in its finished/failed state — the client never renders the final report itself; it just waits for the server round-trip. There's no `onerror` handler, so a dropped connection that the browser's built-in `EventSource` auto-reconnect can't recover (e.g. after the server-side deadline documented in `app.py` is hit) just leaves the page silently stuck showing the last-seen progress list until the user manually reloads.

## Connections

- Talks to two `app.py` routes: `POST /api/v1/runs` (form submit handler) and `GET /api/v1/runs/{run_id}/events` (SSE handler).
- Depends on DOM structure defined in `index.html` (`#batch-form`, `#news`, `#form-status`) and `run.html` (`#events`, `[data-copy]`, the `window.RADAR_*` globals).
- The validation message string is duplicated (not shared) between this file and `app.py`'s `create_run_from_form` — if one changes, the other has to be updated by hand to stay consistent.
