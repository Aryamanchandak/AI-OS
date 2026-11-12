# `create_folder`  ·  group: `utility`

Create one folder inside the server sandbox.

### `create_folder(path: 'str', create_parents: 'bool' = False) -> 'dict'`

Example: `create_folder("reports/2026", create_parents=True)`.

How it works:

- Strips whitespace from `path`.
- Resolves the path through `sandbox._safe(...)`.
- `_safe(...)` joins the path under `mcp_server/sandbox/`, resolves it to a real
  filesystem path, and rejects paths that escape the sandbox.
- Calls `Path.mkdir(...)` to create the directory.

Rules:

- `path` is sandbox-relative.
- `path` cannot be empty.
- The target folder must not already exist.
- If `create_parents=False`, the direct parent must already exist.
- If `create_parents=True`, missing parent directories are created too.

Returns:

- `ok`
- `path`

What can break:

- The path escapes the sandbox, such as `../outside`.
- The target already exists.
- The parent directory is missing and `create_parents=False`.
- The parent path exists but is a file.
- The underlying filesystem refuses the write.
