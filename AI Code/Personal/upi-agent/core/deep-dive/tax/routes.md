# `tax/routes.py`

**Lines:** 428

## Purpose

A FastAPI `APIRouter` that mounts under `/tax` and exposes all HTTP endpoints for the tax module. Handles file uploads, the triage queue, payment classification, bucket management, settings, LLM testing, and Excel export. Single HTTP interface between the browser-side JavaScript (in `templates.py`) and the Python logic in `classifier.py`, `ingest_excel.py`, and `exporter.py`.

## Entry Point

`router` — imported by `dashboard.py` and registered via `app.include_router(tax_router)`.

## Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/tax` or `/tax/` | Returns `TRIAGE_HTML` |
| GET | `/tax/settings` | Returns `SETTINGS_HTML` |
| POST | `/tax/upload` | Saves uploaded file to temp, calls `ingest()`, then `_auto_classify_high_confidence()`, returns stats |
| GET | `/tax/api/queue` | Returns up to `limit` (default 100) unclassified, non-reversal payments, oldest first |
| GET | `/tax/api/payment/{id}/context` | Returns payment + calendar events + past merchant classifications + classifier suggestion + active buckets + queue size + mode |
| POST | `/tax/api/payment/{id}/classify` | Sets category, optionally back-applies to same-merchant unclassified rows, calls `RuleBasedClassifier.learn()` |
| GET | `/tax/api/buckets` | Lists all buckets (including archived) |
| POST | `/tax/api/buckets` | Creates a bucket (max 50 chars, unique name) |
| PATCH | `/tax/api/buckets/{id}` | Renames bucket with cascade to `payments` and `category_rules`; archives/unarchives |
| GET | `/tax/api/settings` | Returns `{mode, llm_endpoint, llm_model}` |
| POST | `/tax/api/settings` | Updates allowed settings keys only; validates `mode` is `'manual'` or `'ai'` |
| POST | `/tax/api/test_llm` | GETs `{endpoint}/v1/models`, returns `{ok, models}` or `{ok, error}` |
| GET | `/tax/export.xlsx` | Calls `export_xlsx()`, returns as `FileResponse` |

## Key Internal Functions

| Name | What it actually does |
|---|---|
| `_db()` | Opens a new `sqlite3.Connection` on every call; returns it with `row_factory = sqlite3.Row` |
| `_now()` | Returns current UTC time as ISO 8601 string |
| `_auto_classify_high_confidence()` | Fetches all unclassified non-reversal/interest/charges rows; applies RuleBasedClassifier; commits those above 0.85 threshold; returns count |

## Design Decisions

- Every route opens a fresh DB connection via `_db()` and closes it in a `finally` block. No connection pool — acceptable for a single-user local app.
- `classify` always calls `RuleBasedClassifier(conn).learn()` regardless of active mode. Learning always uses rules, even when AI mode is active.
- The `PATCH /tax/api/buckets/{id}` rename cascades to both `payments.category` and `category_rules.category` in the same transaction.

## Known Gaps / Risks

- **No authentication or origin check.** Any process on localhost can call these endpoints. Accepted risk since dashboard binds to `127.0.0.1`.
- **Triage queue vs auto-classify discrepancy:** `_auto_classify_high_confidence` excludes `interest` and `charges` from auto-classify. The queue endpoint only excludes `reversal`. So interest/charges rows appear in the queue forever, cannot be auto-classified, and must be manually categorised one-by-one.
- **Upload accepts `.csv` and `.tsv`** in the extension check but `ingest_excel.py` always calls `parse_sbi_file()` which reads as TSV. A proper CSV would parse incorrectly with no clear error.
- **`payment_context` returns the full `payments` row dict,** including all columns — no field allowlist.
- **Export temp file is not cleaned up** — left in the OS temp directory indefinitely.
- **`DB_PATH` duplicated in four files** (`ingest_excel.py`, `migrate.py`, `routes.py`, `exporter.py`) as `Path.home() / ".upi-agent" / "data.db"`. Changing the path requires edits in four places.
