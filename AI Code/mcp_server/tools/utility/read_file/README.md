# `read_file`  ·  group: `utility`

Read one UTF-8 markdown file from the server sandbox.

### `read_file(path: 'str') -> 'dict'`

Example: `read_file("notes.md")`.

Rules:

- `path` is sandbox-relative.
- `path` must end in `.md` or `.markdown`.
- The target must exist and be a regular file.
- Content is decoded as UTF-8 text.

Returns:

- `path`
- `size_bytes`
- `content`
- `encoding`
