# `annual_report`  ·  group: `documents`

1 registered MCP tool(s). Everything for this tool lives in this folder.

### `analyze_annual_report(file_uri: str) -> str`

Run a full Annual Report Analysis (ARA) against a company's annual report PDF. Produces
an institutional-grade markdown document covering financials, governance, related-party
transactions, auditor remarks, management commentary, and more. file_uri: URI returned
as `uri` by upload_file_to_gemini. Returns full ARA markdown text.

**Files:** `logic.py`, `__init__.py` (registration).
