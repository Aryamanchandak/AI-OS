# `web/templates/run.html`

The single-run detail page: it renders one of three entirely different views (live progress, failure, or completed report + full audit trail) from the same route, `GET /runs/{run_id}` (`run_page()` in `app.py`), depending purely on `run.status`. Despite being only 15 lines, it's dense — most of the app's actual data presentation lives here, in long single-line Jinja blocks.

## Template variables expected (from `run_page()`'s context dict)

- `run` — the run dict from `repo.get_run(run_id)`: used for `run.id`, `run.status`, `run.error`.
- `report` — `repo.artifact(run_id, "report")` or, if that's absent, `repo.artifact(run_id, "report_draft")`. Expected shape (a `NewsletterReport`-like dict): `headline`, `dek`, `article_markdown`, `central_case_summary`, `what_changes_the_view` (list), `key_assumptions` (list).
- `validation` — `repo.artifact(run_id, "report_validation")`, expected shape `{valid: bool, errors: [...]}`. Used both to show a warning banner when the shown report is an unvalidated draft, and to gate the "Download .md" link (only shown if `validation.valid`).
- `candidates` — `repo.artifact(run_id, "candidates")`, defaulting to `[]`; each item expected to have `selected` (bool), `reported_premise`, `rationale`, `factual_status`.
- `graph` — `repo.artifact(run_id, "graph")`; expected shape includes `version`, `nodes` (each with `status`, `node_type`, `label`, `time_horizon`), `edges` (each with `status`, `src`, `dst`, `mechanism`, `confidence`), `estimates` (each with `metric`, `low`/`central`/`high`, `unit`, `formula` or `estimate_type`, `caveat`), and `assumptions` (each with `material`, `statement`, `likelihood`, `likelihood_basis`, `if_false_effect`).
- `cases` — `repo.artifact(run_id, "cases")`; used for `cases.central_case.name`, `.weakening_observation`, `.equity_implication_direction`, `.time_horizon`, `.quantification_status`.
- `audit` — `repo.artifacts(run_id)`, i.e. *every* stored artifact version, each with `kind`, `version`, `payload`. Dumped verbatim (`payload|tojson(indent=2)`) inside a collapsible `<details>`.
- `events` — `repo.events_since(run_id)`, full event history from sequence 0; only used in the in-progress branch (each event's `.message`).
- `usage` — `repo.artifact(run_id, "usage")`; fields `calls`, `max_calls`, `searches`, `max_searches`, `input_tokens`, `output_tokens`, `elapsed_seconds`.

## The three branches

The whole `<main>` body is one long `{% if / elif / else %}` on `run.status`:

1. **In progress** — `run.status not in ['completed','completed_with_warnings','report_validation_failed','failed']` (i.e. anything not in `app.py`'s `TERMINAL` set). Shows a `.progress-panel` with an `<ol id="events">` pre-populated from `events`, plus an inline `<script>` block setting `window.RADAR_RUN_ID = {{ run.id|tojson }}` and `window.RADAR_RUNNING = true` — these two globals are exactly what `app.js`'s third block (`if (window.RADAR_RUNNING) { ... EventSource(...) }`) checks for, so this branch is what wires the live SSE stream into the page. New events append live to `#events` client-side; the template's own copy is just the seed state from before the page loaded.

2. **Failed** — `run.status == 'failed'`. Shows `.failure` with `run.error` and a link to `/api/v1/runs/{{ run.id }}/audit` ("Inspect the retained audit JSON") — the `audit()` route in `app.py`.

3. **Everything else** (completed / completed_with_warnings / report_validation_failed) — the full report view:
   - If `validation` exists and `validation.valid` is false, shows a `.warning` banner listing `validation.errors` joined by `; `, explicitly labeling the shown report as unvalidated ("shown for inspection only").
   - If `report` exists, renders the newsletter article: `headline`, `dek`, `article_markdown` (raw text in a `white-space:pre-wrap` block, not Markdown-rendered — it's shown as preformatted text, not converted to HTML), a "Copy report Markdown" button (`data-copy="{{ report.article_markdown|e }}"`, hooked up by `app.js`'s clipboard handler), a conditional "Download .md" link to `/api/v1/runs/{{ run.id }}/report?format=markdown` (only when `validation.valid` — so an invalid/draft report can be read on-page but not downloaded as a file), and an unconditional "Download run JSON" link to `/api/v1/runs/{{ run.id }}/export`.
   - If `cases` exists, renders the central-case summary card and a definition list of direction/horizon/evidence-status, plus (from `report`, not `cases`) "what changes the view" and "key assumptions" bullet lists. This mixes two different artifacts (`cases` and `report`) into one section. The main summary line is actually guarded — `{{ report.central_case_summary if report else cases.central_case.weakening_observation }}` falls back cleanly when `report` is `None`. The `<aside>`'s two loops are not: `{% for item in report.what_changes_the_view %}` and `{% for item in report.key_assumptions %}` dereference `report` directly with no ternary or `if report` guard, and Jinja's default `Undefined` raises on iterating an attribute of `None`. So a run that has a `cases` artifact but no `report` (or `report_draft`) yet would 500 in this section — this coupling is implicit and only safe because in practice a terminal run with `cases` is expected to also have a report.
   - If `candidates` exists (non-empty list), renders a card grid: each candidate's premise, rationale, factual status, and whether it was `selected` (labeled "Selected" or "Runner-up N" via `loop.index`).
   - If `graph` exists, renders active nodes (`node.status == 'active'`) as a horizontal scrolling `.graph-view` strip, non-rejected edges (`edge.status != 'rejected'`) in a collapsible mechanisms/evidence list, then a two-column `.split` section of `estimates` (with an `{% else %}` fallback message "Directional only: defensible numerical inputs were not available" when the list is empty) and material `assumptions` (`if assumption.material`).
   - Always renders an "Audit trail" section: a collapsible `<details>` dumping every artifact in `audit` as pretty-printed JSON (`{{ artifact.payload|tojson(indent=2) }}` inside `<pre>`), with the count of records in the `<summary>`. If `usage` exists, a one-line stats summary (model calls / searches / tokens / elapsed seconds) is shown below it.

## Non-obvious/fragile points

- The status badge in the masthead (`<span class="status status-{{ run.status }}" id="run-status">`) is set once at render time and never updated by JS even though the page reloads itself on completion — so it's always accurate for the render it belongs to, just not live.
- `article_markdown` is displayed as plain preformatted text rather than parsed Markdown — "Markdown" here really means "the report body happens to be Markdown-formatted text," not that the page renders Markdown to HTML.
- The `cases`/`report` cross-referencing described above assumes both are present together; there's no template-level guard against one being set without the other.
- Every artifact version (not just the latest) is dumped into the audit `<pre>` blocks — this can be a large payload for a long-running or heavily revised pipeline run, and it's rendered synchronously on every page load of a completed run (mitigated only by the `<details>` being collapsed by default).

## Connections

- Rendered only by `run_page()` in `app.py`, which assembles all the artifact-lookup variables above from `Repository`.
- Feeds `app.js`'s SSE block (`window.RADAR_RUN_ID`/`RADAR_RUNNING`) and its clipboard block (`data-copy` attribute).
- Links out to four other `app.py` routes: `/api/v1/runs/{id}/audit`, `/api/v1/runs/{id}/report?format=markdown`, `/api/v1/runs/{id}/export`, and implicitly back to `/` via the masthead wordmark link.
- Shares `styles.css` and `app.js` with `index.html` via the same `/static` mount.
