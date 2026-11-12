# Phase 4 — Build & Findings

Build: Readwise CSV export.
Run: code-only session — no processor or schema changes.
Result: **export_readwise_csv() implemented, GET /api/export/csv wired, Export CSV button
in cockpit header. Validated against synthetic DB including commas, double-quotes, empty
passages, and new-status pages. All assertions passed.**

## Verdict (one line)

Phase 4 is code-complete: reviewed highlights export as a Readwise-compatible CSV via one
button click in the cockpit (or `GET /api/export/csv?batch=...`), with correct quoting,
column order, and exclusion logic matching the markdown exporter.

---

## What got built

### `core/export.py` — `export_readwise_csv(db_path, batch, output_dir)`

- SQL JOINs `pages` + `passages`, filters `pages.status='reviewed'`, orders by
  `pages.id, passages.id` for stable book order.
- Post-SQL filter: skips passages where `(edited_text or "").strip()` is empty —
  identical to `_block()`'s filter so markdown and CSV can never disagree on what's
  included.
- Uses `csv.writer(f, quoting=csv.QUOTE_ALL)` — highlights contain commas, em-dashes,
  and quotation marks; the writer handles all escaping.
- Opens with `newline=""`, `encoding="utf-8-sig"` (BOM for Excel compat).
- `None` author and `None` page_number emit as empty string, never the string `"None"`.
- Returns the `Path` written, or `None` if no reviewed passages matched.
- Column order: `Highlight, Title, Author, Note, Location` (spec §9).
- Regenerates the whole CSV on each call (derived artifact, not the durability backstop).

### `server.py` — `GET /api/export/csv?batch=...`

- Calls `export.export_readwise_csv(DB, batch, OUTPUT_DIR)`.
- 404 with a clear message if no reviewed passages exist for the batch.
- Returns `FileResponse` with `media_type="text/csv"` and
  `Content-Disposition: attachment; filename="<batch>.csv"` for browser download.

### Cockpit — Export CSV button

- New `<button id="export-csv" class="pick-btn" ...>Export CSV</button>` in the header
  `.right` div, hidden until a batch is loaded (same timing as Pick Color).
- On click: `window.open(/api/export/csv?batch=<batch>)` — triggers browser download,
  no page reload, no state change.
- Re-uses the existing `.pick-btn` style; no new CSS needed.

---

## Key design decisions

### Why `pages.status='reviewed'` not `passages.accepted`

`passages.accepted` is always 0 — nothing in the codebase ever sets it to 1 (not the
save endpoint, not the processor). Filtering on it yields an empty CSV. `pages.status`
is the canonical acceptance signal.

### Why regenerate the whole CSV

The markdown file uses a page-keyed incremental-update model because `edited_text` is
non-regenerable — losing it costs typing. The CSV is purely derived from what's already
in the DB; regenerating it on demand is simpler and avoids stale-block edge cases.

---

## Validation

Synthetic DB test confirmed:
- Comma and double-quote in highlight text round-trip intact through `csv.reader`.
- Empty-after-strip passages excluded.
- Pages with `status='new'` excluded.
- `NULL` page_number → empty string `""`, not `"None"`.
- Header row: `['Highlight', 'Title', 'Author', 'Note', 'Location']`.
- Row count: header + 1 per non-empty reviewed passage.

**Note:** the live `processed.db` has 0 reviewed pages (all 13 are `status='new'`), so
the live cockpit export path wasn't exercised. To fully close: review at least one page
in the cockpit, then click Export CSV and confirm the download.

---

## Files changed

| file | change |
|---|---|
| `core/export.py` | `export_readwise_csv()` added; `import csv, sqlite3` added |
| `server.py` | `GET /api/export/csv` endpoint added |
| `static/index.html` | `<button id="export-csv" ...>` added in header `.right` |
| `static/review.js` | `els.exportCsv` ref; `hidden` toggle in `render()`; click handler |
| `Phase4.md` | spec/brief for this phase |
| `Phase4-findings.md` | this file |
