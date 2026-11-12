# `tax/exporter.py`

**Lines:** 154

## Purpose

Queries all rows from `payments`, writes them to a two-sheet `.xlsx` file using `openpyxl`, and returns the file path as a string. The first sheet (`Transactions`) is a formatted table of every payment. The second sheet (`Summary`) contains per-bucket totals driven by `SUMIFS` formulas so that the spreadsheet remains live when a CA re-filters or re-sorts it.

## Entry Point

`export_xlsx(db_path, out_path)` — called by `routes.py`'s `/tax/export.xlsx` handler. Can be run directly (`python exporter.py`) to write a timestamped file to the system temp directory.

## Data Flow

1. Connects to `data.db`, queries all rows from `payments` ordered by `occurred_at` then `id`. Uses `COALESCE` to substitute display defaults (`'(unclassified)'` for NULL category, `'sms'` for NULL source, `'upi'` for NULL txn_kind).
2. Closes the connection immediately after fetching.
3. Creates an `openpyxl.Workbook`. First worksheet is titled `Transactions`.
4. Writes a styled header row (bold Arial, grey fill), then all data rows. Formats column D (Amount) with Indian Rupee number format and red negative values.
5. Sets column widths, freezes row 1, enables autofilter over all data.
6. Creates a `Summary` worksheet. Derives distinct bucket names from the in-memory rows list (not a DB query), alpha-sorted with `'(unclassified)'` pushed to the bottom.
7. For each bucket, writes `SUMIFS` formulas for debits, credits, and a `COUNTIF` for count. Adds a `SUM` totals row.
8. If `out_path` is None, generates a timestamped filename in `tempfile.gettempdir()`.
9. Saves the workbook and returns the path string.

## Key Function

| Name | What it actually does |
|---|---|
| `export_xlsx(db_path, out_path)` | Reads all payments, writes two-sheet .xlsx, returns file path |

## Design Decisions

- Formulas in the Summary sheet reference the Transactions sheet by exact sheet name (`Transactions!D2:D{last_data_row}`). If the user renames the sheet in Excel, the formulas break.
- Currency number format uses `"₹"` as a prefix literal — renders correctly in modern Excel.
- `rows` is fetched as a list and iterated twice (once for Transactions sheet, once to collect unique bucket names for Summary sheet) — full result set is held in memory.

## Known Gaps / Risks

- **Totals row range formula:** The SUM formula is correct but fragile if the bucket list ever starts at a different row.
- **Temp file not cleaned up:** `routes.py` passes the temp path to `FileResponse`. FastAPI's `FileResponse` does not delete temp files by default; the file persists in the OS temp directory indefinitely.
- **No date range filtering:** The export always contains every row in the entire database — no fiscal year or date range parameter.
- **Buckets derived from payment data only:** If a bucket exists in the `buckets` table but has no payments, it will not appear in the Summary sheet.
