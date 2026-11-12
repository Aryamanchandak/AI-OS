# 2026-07-05 Utility Markdown Files Change Log

This note records the approved restructuring and behavior change for the former
`tools/utility/files/` multi-tool folder.

## Decision

- Split the former `files` feature folder into one folder per MCP tool.
- Keep the public MCP tool names unchanged:
  - `read_file`
  - `list_dir`
  - `create_file`
  - `update_file`
  - `edit_file`
- Add missing markdown workflow tools:
  - `suggest_file_path`
  - `create_folder`
  - `append_file`
- Focus these file-writing tools on sandbox markdown files for now.
- Do not add arbitrary 1 MB read/write caps in this pass.
- Keep larger document formats such as `.docx` out of these tools; those should
  get dedicated tools later.

## Code Changes

### New Tool Folders

- `tools/utility/read_file/`
- `tools/utility/list_dir/`
- `tools/utility/suggest_file_path/`
- `tools/utility/create_folder/`
- `tools/utility/create_file/`
- `tools/utility/append_file/`
- `tools/utility/update_file/`
- `tools/utility/edit_file/`

Each folder now contains its own `tool.py`, `__init__.py`, and `README.md`.

### Removed Former Multi-Tool Source Folder

- Removed the registered source files from `tools/utility/files/`.

### `sandbox.py`

- Added `MARKDOWN_SUFFIXES`.
- Added `_safe_markdown_path(...)`, which keeps the existing sandbox escape guard
  and additionally requires `.md` or `.markdown`.

### Markdown File Tool Behavior

- `read_file`, `create_file`, `update_file`, and `edit_file` now require
  markdown paths ending in `.md` or `.markdown`.
- `read_file`, `update_file`, and `edit_file` now explicitly require an existing
  regular file.
- `create_file` now explicitly requires an existing parent directory.
- `list_dir` now explicitly requires an existing directory.
- `edit_file` now rejects an empty `find` string.
- File content remains UTF-8 text.

### Added Workflow Tool Behavior

- `suggest_file_path` proposes an unused markdown filename in an existing
  sandbox directory without creating anything.
- `create_folder` creates one sandbox directory, with optional parent-directory
  creation through `create_parents=True`.
- `append_file` appends UTF-8 text to an existing markdown file, writing a
  separator first when the file already has content.
- `create_file` documentation now explicitly explains the filesystem write path:
  sandbox resolution, markdown suffix check, existence checks, and
  `Path.write_text(content, encoding="utf-8")`.

## Caveats

- There is no hard size cap yet. Very large markdown content may still hit MCP,
  client, or model context limits, even though the tool itself does not impose a
  1 MB boundary.
- Binary files and rich document formats are intentionally out of scope for
  these tools.
