# `edit_file`  ·  group: `utility`

Find and replace text inside one UTF-8 markdown file in the server sandbox.

### `edit_file(path: 'str', find: 'str', replace: 'str', replace_all: 'bool' = False) -> 'dict'`

Example: `edit_file("hello.md", "old", "new")`.

Rules:

- `path` is sandbox-relative.
- `path` must end in `.md` or `.markdown`.
- The target must exist and be a regular file.
- `find` cannot be empty.
- If `find` appears more than once, pass `replace_all=True`.
- Content is read and written as UTF-8 text.

Returns:

- `ok`
- `path`
- `replacements`
- `size_bytes`
- `encoding`
