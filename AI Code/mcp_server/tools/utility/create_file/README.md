# `create_file`  ·  group: `utility`

Create one UTF-8 markdown file in the server sandbox.

### `create_file(path: 'str', content: 'str') -> 'dict'`

Example: `create_file("hello.md", "# Hello\n")`.

How it works:

- Receives a sandbox-relative `path` and a string `content`.
- Resolves `path` through `sandbox._safe_markdown_path(...)`.
- `_safe_markdown_path(...)` calls `sandbox._safe(...)`.
- `_safe(...)` joins the provided path under `mcp_server/sandbox/`, resolves the
  real filesystem path, and rejects it if the resolved path is outside the
  sandbox.
- `_safe_markdown_path(...)` then requires the resolved path to end in `.md` or
  `.markdown`.
- `create_file` checks that the target does not already exist.
- `create_file` checks that the parent directory already exists and is a
  directory.
- It writes the file with `Path.write_text(content, encoding="utf-8")`.
- It returns metadata after writing.

Rules:

- `path` is sandbox-relative.
- `path` must end in `.md` or `.markdown`.
- The target file must not already exist.
- The parent directory must already exist.
- Content is written as UTF-8 text.

Returns:

- `ok`
- `path`
- `size_bytes`
- `encoding`

What can break:

- The path escapes the sandbox, such as `../outside.md`.
- The path does not end in `.md` or `.markdown`.
- The file already exists.
- The parent directory does not exist.
- The parent path exists but is a file.
- The content is too large for the MCP/client request before the tool receives it.
- The filesystem refuses the write.
