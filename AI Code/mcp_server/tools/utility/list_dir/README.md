# `list_dir`  ·  group: `utility`

List one directory inside the server sandbox.

### `list_dir(path: 'str' = '.') -> 'dict'`

Example: `list_dir(".")`.

Rules:

- `path` is sandbox-relative.
- The target must exist and be a directory.
- This tool lists names and basic metadata only; it does not read file content.

Returns:

- `path`
- `count`
- `names`
- `entries`
