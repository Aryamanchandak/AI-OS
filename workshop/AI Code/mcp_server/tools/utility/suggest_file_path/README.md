# `suggest_file_path`  ·  group: `utility`

Suggest an unused markdown filename inside an existing sandbox directory.

### `suggest_file_path(purpose: 'str', directory: 'str' = '.', extension: 'str' = 'md') -> 'dict'`

Example: `suggest_file_path("RBI NBFC master direction notes", "research")`.

`purpose` is the reason the caller wants a file, written as plain text. This
tool uses it only to generate a filename. It does not understand project
semantics, choose the correct folder, search the computer, or decide where a
document belongs.

Folder choice is external to this tool. The caller must already know the target
directory, usually by using `list_dir` and its own judgment.

How it works:

- Uses `purpose` to build a lowercase slug filename.
- Resolves `directory` through `sandbox._safe(...)`.
- Requires the directory to already exist.
- Requires `extension` to be `.md` or `.markdown`.
- Checks whether the proposed filename exists.
- If it exists, tries `name-2.md`, `name-3.md`, and so on until it finds an
  unused path.
- Returns a canonical sandbox-relative suggested path but does not create any
  file or folder.

Current responsibility boundary:

- Chooses a safe unused filename inside a directory that was already chosen.
- Does not find the correct folder.
- Does not classify files or directories.
- Does not maintain a directory graph or file index.
- Does not tell the LLM where a document should belong.

Returns:

- `path`
- `directory`
- `filename`
- `exists`
- `reason`

What can break:

- `purpose` is empty.
- `directory` escapes the sandbox.
- `directory` does not exist.
- `directory` points to a file.
- `extension` is not markdown.
