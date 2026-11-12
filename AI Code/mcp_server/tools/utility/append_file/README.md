# `append_file`  ·  group: `utility`

Append UTF-8 text to an existing markdown file in the server sandbox.

### `append_file(path: 'str', content: 'str', separator: 'str' = '\\n') -> 'dict'`

Example: `append_file("research/rbi-notes.md", "## Source 2\n\nMore notes.")`.

How it works:

- Resolves `path` through `sandbox._safe_markdown_path(...)`.
- `_safe_markdown_path(...)` keeps the file under `mcp_server/sandbox/` and
  requires `.md` or `.markdown`.
- Requires the file to already exist.
- Opens the file in append mode with UTF-8 encoding.
- If the file already has content, writes `separator` first.
- Writes `content` after the separator.

Rules:

- `path` is sandbox-relative.
- `path` must end in `.md` or `.markdown`.
- The target must exist and be a regular file.
- `content` cannot be empty.
- `separator` defaults to one newline.

Returns:

- `ok`
- `path`
- `bytes_appended`
- `size_bytes`
- `encoding`

What can break:

- The path escapes the sandbox.
- The path is not markdown.
- The file does not exist.
- The path points to a directory.
- The append makes the markdown structurally messy because the caller did not
  inspect the existing file first.
