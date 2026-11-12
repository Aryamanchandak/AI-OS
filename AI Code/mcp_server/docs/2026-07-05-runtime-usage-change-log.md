# 2026-07-05 Runtime And Usage Change Log

This note records the changes made during the first top-level runtime pass.

## MCP Server Runtime

### `mcp_server.py`

- Changed startup registration to take one local snapshot of registered tools:
  `entries = get_all()`.
- Registered FastMCP tools from that snapshot.
- Updated startup logging to use the same snapshot.
- Changed `list_tools()` so it reads from `tool_registry.get_all()` instead of
  FastMCP private internals such as `mcp._tool_manager._tools`.
- Added `list_tools` manually to the returned `utility` group because it is
  registered directly in `mcp_server.py`, not through `tool_registry`.

Reason: the MCP server should use its own registry as the source of truth and
avoid depending on private FastMCP implementation details.

### `tool_registry.py`

- Removed an unused `field` import.
- Made `register(group=...)` idempotent for the exact same function object in
  the exact same group.
- Existing name-collision checks remain in place through
  `assert_no_name_collisions()`.

Reason: repeated imports or development reloads should not duplicate the same
tool entry, while two different tools with the same name should still fail fast.

## Usage Logging

### `usage.py`

- Replaced JSON counter storage with a simple markdown event log.
- `usage.bump(provider, field="count")` keeps the same caller-facing API.
- Events now append to `usage.md` as a markdown table with:
  - UTC timestamp
  - provider
  - field
- Usage logging is best-effort and catches all exceptions so logging cannot
  break the calling tool.

Reason: keep current usage tracking readable and low-risk. Future nightly
plumbing can parse the markdown log and move events into SQLite or another
store without making the MCP runtime depend on that store.

### `usage.md`

- Created as the local runtime usage log.
- A smoke-test row was briefly written and then removed.
- The file currently contains only the markdown header/table structure.

## Ignore Rules

### `.gitignore`

Added ignore rules for local/runtime files:

- Python cache files
- `.DS_Store`
- `.venv/`
- `.pytest_cache/`
- `usage.json`
- `usage.md`
- `gateway.log`
- sandbox runtime contents, while preserving `sandbox/.gitkeep`

Reason: keep generated/runtime artifacts out of versioned project state.

## Raw Data Note

### `/Users/aryamanchandak/Documents/AI Code/Database/Raw Data/chats/README.md`

- Added a short README describing raw chat storage.
- Clarified that raw chat capture should be automatic runtime behavior, not an
  MCP tool and not a model-selectable action.
- Stated that every gateway chat request should eventually produce a raw record,
  including failures.

Reason: record the architectural decision without implementing the full capture
pipeline yet.

## Verification

- Ran Python compile checks for:
  - `mcp_server.py`
  - `tool_registry.py`
  - `usage.py`
- Used `PYTHONPYCACHEPREFIX=/tmp/mcp_server_pycache` so bytecode writes stayed
  inside an allowed temporary path.
- Verified that `usage.bump(...)` can create/write the markdown usage log.
