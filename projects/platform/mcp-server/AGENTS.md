# MCP Server Working Notes

This repo is being reviewed and improved block by block with the user.

## Collaboration Workflow

- Do not make broad changes before explaining the lay of the land for the current
  block.
- When explaining a tool, describe the actual mechanics:
  - what input the model/caller provides;
  - what path, URL, provider, or object that input becomes;
  - the exact operation that creates, reads, writes, fetches, or mutates data;
  - what is returned;
  - what can break;
  - what the tool does not know or decide.
- Avoid vague summaries like "takes a path" when the unresolved question is how
  that path is chosen, resolved, communicated, or written on disk.
- For each block:
  1. Inspect the files and summarize what they do.
  2. Suggest concrete changes and explain why.
  3. Wait for user preferences, corrections, or additions.
  4. Make only the approved changes.
  5. Verify where practical.
  6. Record meaningful completed work in `docs/`.

## Current Direction

- Keep this repo MCP-focused.
- FastMCP remains the MCP serving surface.
- The MCP server should use its own `tool_registry` as the source of truth for
  known tools, not FastMCP private internals.
- Do not add HTTP, SQLite, or additional service dependencies to MCP runtime
  paths unless explicitly approved.
- Keep telemetry simple for now:
  - `usage.py` appends best-effort markdown rows to `usage.md`.
  - Nightly plumbing can parse and move usage data elsewhere later.
  - Logging must not break tool execution.
- Full chat/tool-call capture is a later architecture item, not a current
  priority. When implemented, it should be automatic runtime behavior, not an
  MCP tool a model chooses to call.
- Future TODOs are consolidated in root `TODO.md`.
- File/directory intelligence is a future architecture item, not a current MCP
  tool. See root `TODO.md`.

## Important Existing Decisions

- Raw chats should eventually be stored under:
  `/Users/aryamanchandak/Documents/AI Code/Database/Raw Data/chats/`
- Raw chat capture should include user prompt, agent steps where available, tool
  calls, status, failures, and success metadata.
- Full tool output does not need to be the first priority, but failures and
  success logs matter.
- `llm_gateway` is the eventual place for provider access and durable telemetry,
  but do not integrate it into this MCP runtime yet.
- Current markdown file tools are sandbox-scoped. They do not know the full
  filesystem, maintain a directory graph, watch directories, classify folder
  purpose, or automatically choose where a new document belongs.

## Work Already Completed

See `docs/2026-07-05-consolidated-change-log.md`.

Completed so far:

- Added `.gitignore`.
- Made `mcp_server.py` avoid FastMCP private internals in `list_tools()`.
- Made `tool_registry.register(...)` skip exact duplicate registrations.
- Converted `usage.py` from JSON counters to a simple markdown usage log.
- Added a Raw Data chats README describing future mandatory raw chat capture.
- Reviewed shared Gemini/file-upload handling and kept one MCP-facing Gemini
  upload path.
- Updated `web_search` to use Brave Search only.
- Updated `fetch_url` to validate URLs and enforce a hard 30-second timeout.
- Split the former `tools/utility/files/` folder into one folder per markdown
  file tool.
- Current markdown file workflow tools:
  - `suggest_file_path`
  - `create_folder`
  - `create_file`
  - `read_file`
  - `append_file`
  - `update_file`
  - `edit_file`
  - `list_dir`
- `create_file` creates a real file at the `Path.write_text(content,
  encoding="utf-8")` call after sandbox and markdown validation.
- Added root `TODO.md` to consolidate future TODOs, including the future
  watcher/graph/index/folder-selection architecture.

## Suggested Block Order

1. Top-level runtime files: complete for now.
2. `shared/`: first pass complete; revisit with `file_upload` when approved.
3. `tools/utility/`: continue tool-by-tool.
4. Other tool groups one by one.
5. Docs cleanup after behavior is clearer.

## Current Next Step

- Continue the file workflow review tool-by-tool.
- `create_file` mechanics have been explained and approved.
- Next likely file-workflow tools to review: `suggest_file_path`,
  `create_folder`, `append_file`, `read_file`, `update_file`, `edit_file`, and
  `list_dir`, one at a time.
