# `capture`  ·  group: `raw_data`

2 registered MCP tool(s). Everything for this tool lives in this folder.

### `capture_raw_data(source: 'str', content: 'str', authored: 'bool' = False, metadata: 'dict[str, Any] | None' = None) -> 'dict[str, Any]'`

Write immutable bronze content through Raw Data's sanctioned capture() path.

### `raw_data_status(target: 'str' = 'kg', max_age_days: 'int' = 3) -> 'dict[str, Any]'`

Return ledger-based pending and staleness status without reading bronze content.

**Files:** `logic.py`, `__init__.py` (registration).
