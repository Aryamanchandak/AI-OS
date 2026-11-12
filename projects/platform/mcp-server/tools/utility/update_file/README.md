# `update_file`  ·  group: `utility`

Overwrite one existing UTF-8 markdown file in the server sandbox.

### `update_file(path: 'str', content: 'str') -> 'dict'`

Example: `update_file("hello.md", "# Updated\n")`.

Rules:

- `path` is sandbox-relative.
- `path` must end in `.md` or `.markdown`.
- The target must exist and be a regular file.
- Content is written as UTF-8 text.

Returns:

- `ok`
- `path`
- `size_bytes`
- `encoding`
