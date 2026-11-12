# `misc`  ·  group: `utility`

2 registered MCP tool(s). Everything for this tool lives in this folder.

### `currency_convert(amount: 'float', from_currency: 'str', to_currency: 'str') -> 'dict'`

Convert money between ISO-3 currencies via frankfurter.dev. Example:
currency_convert(100, "USD", "INR").

### `get_time(timezone: 'str' = 'UTC') -> 'dict'`

Current time in a named IANA timezone. Example: get_time("Asia/Kolkata").

**Files:** `tool.py`, `__init__.py` (registration).
