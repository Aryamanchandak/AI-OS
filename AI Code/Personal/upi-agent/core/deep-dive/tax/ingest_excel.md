# `tax/ingest_excel.py`

**Lines:** 132

## Purpose

Orchestrates the ingestion of a parsed SBI file into the `payments` table in `data.db`. It deduplicates against existing rows by `ref_no`, builds an INSERT dynamically based on which optional columns actually exist in the schema, then fires the brain reactor as a best-effort side-effect. Returns a stats dict that the upload route surfaces to the user.

## Entry Point

`ingest(file_path, db_path)` — called by `routes.py`'s upload handler. Can be invoked directly (`python ingest_excel.py file.xls`) for one-shot terminal ingestion.

## Data Flow

1. Calls `parse_sbi_file(file_path)` → `List[ParsedRow]`.
2. Opens `data.db` with `sqlite3.connect`. Queries `PRAGMA table_info(payments)` to detect which optional columns exist.
3. For each parsed row: if `ref_no` is set and already exists in `payments.ref_no`, increments `matched` counter and optionally promotes `source` from `'sms'` to `'both'`. Continues to next row (no insert).
4. For new rows: builds `cols` and `vals` lists dynamically, appending optional columns only if the schema has them. Inserts with a plain `INSERT INTO` (no `OR IGNORE` — dedup is handled by the explicit lookup above).
5. Commits and closes the connection.
6. Fires `brain.reactor.on_new_payments(new_ids)` inside a bare `except Exception: pass` block.
7. Returns `{'parsed', 'matched_existing', 'inserted', 'skipped', 'new_payment_ids'}`.

## Key Function

| Name | What it actually does |
|---|---|
| `ingest(file_path, db_path)` | Full parse-dedup-insert pipeline; returns stats dict |

## Design Decisions

- `confidence` is hardcoded to `1.0` for all Excel-ingested rows — bank statement data is considered authoritative. SMS-ingested rows use the parser's own confidence value.
- `source` is set to `'excel'` on insert. If the same transaction was already ingested via SMS, the existing row's source is promoted to `'both'` — creating a cross-source verification signal.
- Brain reactor is called after the connection is closed to avoid locking conflicts.

## Known Gaps / Risks

- **Silent brain failure:** `except Exception: pass` swallows all errors from the brain reactor. If anomaly detection or narrative generation fails, the user gets no indication.
- **No ref_no dedup for rows without a ref_no:** Rows where `ref_no is None` (some ATM, interest, charges rows) are inserted every time. Re-uploading the same statement will duplicate those rows.
- **`skipped` always 0:** The returned stats dict includes `'skipped': skipped` but nothing ever increments `skipped`. This is a silent lie in the stats output.
- Schema detection (`PRAGMA table_info`) is re-run on every `ingest()` call.
