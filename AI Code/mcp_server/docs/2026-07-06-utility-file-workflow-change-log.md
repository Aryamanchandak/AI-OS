# 2026-07-06 Utility File Workflow Change Log

This note records the follow-up file-workflow additions for sandbox markdown
files.

## Decision

- Keep file creation and editing markdown-focused.
- Add a tool to create folders.
- Add a tool to suggest unused markdown paths.
- Add a tool to append to existing markdown files.
- Make `create_file` documentation explicit about how the file is actually
  created on disk.

## New Tools

### `tools/utility/create_folder/`

- Adds `create_folder(path, create_parents=False)`.
- Creates sandbox directories through `Path.mkdir(...)`.
- Rejects blank paths, sandbox escapes, existing targets, and invalid parents.

### `tools/utility/suggest_file_path/`

- Adds `suggest_file_path(purpose, directory=".", extension="md")`.
- Builds a slug filename from `purpose`.
- Requires an existing sandbox directory.
- Requires `.md` or `.markdown`.
- Returns the first unused candidate path without creating anything.
- Returns the candidate as a canonical sandbox-relative path, even when the
  caller supplied a non-canonical but sandbox-safe directory such as
  `research/..`.
- Does not choose the correct folder; the caller must already provide a
  directory.

### `tools/utility/append_file/`

- Adds `append_file(path, content, separator="\\n")`.
- Requires an existing markdown file.
- Rejects empty content.
- Appends a separator first when the file already has content.

## Documentation

- Expanded `tools/utility/create_file/README.md` to explain the exact write path:
  sandbox resolution, markdown suffix check, existence checks, parent-directory
  checks, and `Path.write_text(content, encoding="utf-8")`.
- Expanded `tools/utility/suggest_file_path/README.md` to clarify that `purpose`
  is only filename input and that folder discovery is outside the current tool.

## Caveats

- `suggest_file_path` does not create folders or files.
- `suggest_file_path` does not discover the correct folder or classify where a
  document belongs.
- `append_file` can make a markdown document messy if the caller does not inspect
  existing structure first.
- There is still no hard content-size cap; MCP/client/model payload limits may
  still be hit before tool code runs.
