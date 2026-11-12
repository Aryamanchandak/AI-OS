# `lease_deed`  ·  group: `finance`

3 registered MCP tool(s). Everything for this tool lives in this folder.

### `build_clause_report(pdf_bytes: bytes) -> bytes`

Analyse critical clauses in a lease deed PDF and build a formatted Word document.
Clauses are grouped and colour-coded by risk category. Returns docx bytes. Use this when
you only need the clause report without the rent roll.

### `build_rent_roll(pdf_bytes: bytes) -> bytes`

Extract contract data from a lease deed PDF and build a 41-column rent roll Excel file.
Returns xlsx bytes, with date formatting, percentage columns, and frozen panes. Use this
when you only need the rent roll without clause analysis.

### `process_lease_deed(pdf_bytes: bytes) -> dict`

Full end-to-end lease deed review. Produces both a rent roll Excel and a critical clause
report Word document in one call. Returns: { "rent_roll_excel": bytes,
"clause_report_docx": bytes } Use build_rent_roll or build_clause_report individually
for partial workflows.

**Files:** `logic.py`, `__init__.py` (registration).
