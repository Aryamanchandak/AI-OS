# MCP Server TODO

This is the root source of truth for non-immediate TODOs in this repo. Keep
block-level completed work in `docs/` change logs; keep future work here.

## File Directory Intelligence

This needs to be built, but not as a quick MCP tool bolted onto the current
markdown file utilities.

### Problem

The current file tools can operate only on paths the caller already knows:

- `list_dir` shows one sandbox directory.
- `suggest_file_path` suggests a filename inside a directory already chosen by
  the caller.
- `create_folder` creates a folder path the caller already chose.
- `create_file`, `append_file`, `read_file`, `update_file`, and `edit_file`
  operate on explicit sandbox-relative file paths.

They do not answer the real question:

> Given a new document or task, where should this file live?

### Current Manual Workflow

Today the caller has to do this manually:

1. call `list_dir`;
2. inspect available folders;
3. choose a folder;
4. optionally call `suggest_file_path`;
5. create, append, or edit the markdown file.

This is workable for now, but it is not real file-location intelligence.

### Current Sandbox Boundary

Current file tools are limited to:

```text
mcp_server/sandbox/
```

Paths are resolved through `sandbox._safe(...)`, which joins the model-provided
path under that sandbox and rejects paths that resolve outside it.

That means the current tools do not know the full computer filesystem. They do
not know the user's Documents tree, project tree, external database folders, or
other app directories unless files are intentionally placed under the sandbox or
new architecture expands the boundary.

### Communication Problem

Even if a directory tree exists, the model cannot reason about it unless the
runtime sends useful information.

Open questions:

- What directory tree is in scope: only `mcp_server/sandbox/`, the whole MCP
  repo, the wider `AI Code/` workspace, or user-selected roots?
- How much file metadata is safe and useful to expose?
- Should the model see raw directory listings, summarized folder descriptions,
  graph search results, or ranked candidate paths?
- How are updates communicated: on demand scan, background watcher, or durable
  index?
- How do we prevent leaking sensitive paths or contents into prompts/tool
  outputs unnecessarily?
- How do we keep context small enough for model use?

### Likely Shape

Build a separate file/directory intelligence layer:

- Watch selected roots with something like `watchdog`.
- Maintain a durable graph/index of folders and files.
- Track metadata such as path, parent, children, extension, size, timestamps,
  and maybe lightweight text summaries where allowed.
- Derive folder-purpose summaries from names, contained files, and user-approved
  annotations.
- Expose a narrow query interface that returns ranked candidate folders/files,
  not the whole tree.

Possible future capabilities:

- Find the best folder for a new document.
- Suggest filenames based on existing naming patterns in that folder.
- Detect likely duplicate or related files.
- Explain why a folder was suggested.
- Keep file-content exposure separate from file-metadata exposure.
- Answer where a file should go without dumping an entire directory tree into
  the model context.

### Not Current Behavior

- No full-computer scan.
- No background watcher.
- No directory graph.
- No semantic folder classifier.
- No automatic folder choice.
- No model-visible global filesystem map.

The current `suggest_file_path` tool is only a small filename helper inside an
already chosen sandbox directory. It is not directory intelligence.

## Podcast Pipeline

The podcast pipeline folder currently holds MCP-side scaffolds, contracts, claim
boundaries, automation shape, and a SQLite storage adapter. The remaining work
below is intentionally tracked without implementing it here.

### External Dependencies

- `LLM_Gateway/`: wire Deepgram-backed transcription before the MCP
  transcription tool is made live. The tool stub in `tools/transcribe.py` should
  call the gateway once that integration exists. The `LLM_Gateway/` folder is
  not present in this workspace, so this remains a tracked dependency only.
- `LLM_Gateway/`: move model selection into a shared config so
  `tools/summarise.py` and any future LLM-backed podcast tools do not hardcode
  provider/model choices.
- `mcp_server/research_tools/`: keep the research-specific claim extraction and
  verification integration blocked until the research MCP project is
  intentionally brought into this server. The generic stubs in `claims/` are
  left in place on purpose.

### Downstream Follow-Up

- `mcp_server/groups/media/`: once provenance wiring is confirmed there, add
  `log_tool_execution()` calls to each `groups/media/podcast_*.py` tool so every
  run is written to `Database/sqlite/podcast_pipeline.db`.

### Current Local Status

- `storage/client.py` already writes to `Database/sqlite/podcast_pipeline.db`.
- `tools/transcribe.py`, `tools/summarise.py`, and `tools/research.py` are still
  MCP boundary scaffolds.
- `claims/extraction/service.py` and `claims/verification/service.py` are
  generic service boundaries, not server-wired implementations.
