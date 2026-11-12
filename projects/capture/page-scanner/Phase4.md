Read CLAUDE.md and spec.md before writing any code.
Phase 3 is complete. We are doing Phase 4.

READWISE CSV EXPORT:

Goal: from reviewed pages in processed.db, produce a Readwise-compatible bulk-import CSV
for a batch. This is the "10-line export" called out in spec §9.

Readwise bulk-import CSV columns (in order): Highlight, Title, Author, Note, Location
- Highlight: passage.edited_text (the version the user typed/confirmed)
- Title: pages.batch
- Author: pages.author (empty string if null)
- Note: always empty
- Location: pages.page_number (integer, empty string if null)

Selection criteria:
- pages.status = 'reviewed' (the `accepted` column is never written; don't use it)
- passage.edited_text is non-empty after strip() — identical filter to _block() in export.py
- Order by page_id ASC, passage_id ASC (stable book order)
- One CSV row per passage (a page with 3 highlights = 3 rows sharing Title/Author/Location)

Implementation:

1. core/export.py — add export_readwise_csv(db_path, batch, output_dir):
   - Import csv, sqlite3 as needed (both already in use in the module)
   - SQL: JOIN pages + passages WHERE pages.batch=? AND pages.status='reviewed'
     ORDER BY pages.id, passages.id
   - Use csv.writer(f, quoting=csv.QUOTE_ALL) — highlights will contain commas and quotes
   - Open with newline="" and encoding="utf-8-sig" (BOM for Excel compat)
   - None → "" for author and page_number (never emit "None")
   - Return the Path written (or None if no rows matched)

2. server.py — add GET /api/export/csv?batch=...:
   - Calls export_readwise_csv(DB, batch, OUTPUT_DIR)
   - If None returned (no reviewed passages for that batch): raise HTTPException(404, "no reviewed passages")
   - Read the written CSV file and return it as FileResponse with:
     - media_type="text/csv"
     - headers={"Content-Disposition": f'attachment; filename="{batch}.csv"'}

3. static/index.html — add "Export CSV" button in the .right div of the header:
   - <button id="export-csv" class="pick-btn" type="button">Export CSV</button>
   - Hidden by default; shown once a batch is loaded (same timing as pick-color)

4. static/review.js — wire up the Export CSV button:
   - On click: window.open(`/api/export/csv?batch=${encodeURIComponent(state.batch)}`)
   - No page reload, no state change

5. static/review.css — no new styles needed (pick-btn already covers it)

OUT OF SCOPE — do not implement:
- Readwise API push
- Auto color detection
- Underline-erase (horizontal morphology)
- Any new processor or schema changes

Validation (do this before declaring done):
- Create a synthetic in-memory SQLite DB with 2 reviewed pages (one with a comma and
  a double-quote in the highlight text), run export_readwise_csv(), and assert the
  CSV round-trips correctly via csv.reader. Print the CSV to stdout so the result
  is visible. This substitutes for a live cockpit test since the real DB has no
  reviewed pages yet.

Exit condition: export_readwise_csv() produces a valid CSV with correct columns for
the synthetic test. Stop and report. Do not proceed without explicit instruction.
