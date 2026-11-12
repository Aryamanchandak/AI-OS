# `credit_one_pager`  ·  group: `finance`

1 registered MCP tool(s). Everything for this tool lives in this folder.

### `generate_credit_one_pager(file_uri: str) -> str`

Generate a concise credit one-pager from an annual report PDF. Focused on debt
serviceability, leverage, liquidity, and governance risks. file_uri: URI returned as
`uri` by upload_file_to_gemini. Returns structured markdown suitable for quick credit
screening. Use generate_credit_note for a full multi-section internal credit note.

**Files:** `logic.py`, `__init__.py` (registration).
