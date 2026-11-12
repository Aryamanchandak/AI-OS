# 2026-07-05 Consolidated Change Log

This document collates the block-level change logs from the July 5, 2026 MCP
server review. It is intended as the single handoff note for continuing the work
in a fresh chat.

Source notes consolidated here:

- `docs/2026-07-05-runtime-usage-change-log.md`
- `docs/2026-07-05-shared-gemini-file-upload-change-log.md`
- `docs/2026-07-05-utility-web-search-change-log.md`
- `docs/2026-07-05-utility-fetch-change-log.md`
- `docs/2026-07-05-utility-markdown-files-change-log.md`
- `docs/2026-07-06-utility-file-workflow-change-log.md`
- `TODO.md`

The larger per-tool folder restructure remains documented separately in
`docs/MIGRATION_LOG.md` and `docs/ARCHITECTURE.md`.

## Current Working Direction

- Keep the repo MCP-focused.
- FastMCP remains the serving surface.
- `tool_registry` remains the source of truth for known tools.
- Avoid FastMCP private internals.
- Keep telemetry simple and best-effort.
- Do not add HTTP, SQLite, or additional runtime service dependencies unless
  explicitly approved.
- Review utility tools one at a time.
- Preferred future utility shape: one MCP tool per folder.
- For simple tools, inline registration in `tool.py` is preferred:
  `@register(group="utility")`.
- For tool reviews, explain the actual mechanics: caller input, resolution or
  provider path, the exact operation that creates/reads/writes/fetches data, the
  return value, failure modes, and what the tool does not decide.

## Runtime And Registry

### `mcp_server.py`

- Startup now takes one local snapshot of registered tools:
  `entries = get_all()`.
- FastMCP tools are registered from that snapshot.
- Startup logging uses the same snapshot.
- `list_tools()` now reads from `tool_registry.get_all()` instead of FastMCP
  private internals such as `mcp._tool_manager._tools`.
- `list_tools` is added manually to the returned `utility` group because it is
  registered directly in `mcp_server.py`, not through `tool_registry`.

Reason: the MCP server should use its own registry as the source of truth and
avoid depending on private FastMCP implementation details.

### `tool_registry.py`

- Removed an unused `field` import.
- Made `register(group=...)` idempotent for the exact same function object in
  the exact same group.
- Existing name-collision checks remain in place through
  `assert_no_name_collisions()`.

Reason: repeated imports or development reloads should not duplicate the same
tool entry, while two different tools with the same name should still fail fast.

## Usage Logging

### `usage.py`

- Replaced JSON counter storage with a simple markdown event log.
- `usage.bump(provider, field="count")` keeps the same caller-facing API.
- Events now append to `usage.md` as a markdown table with:
  - UTC timestamp
  - provider
  - field
- Usage logging is best-effort and catches all exceptions so logging cannot
  break the calling tool.

Reason: keep current usage tracking readable and low-risk. Future nightly
plumbing can parse the markdown log and move events into SQLite or another store
without making the MCP runtime depend on that store.

### `usage.md`

- Created as the local runtime usage log.
- A smoke-test row was briefly written and then removed.
- The file currently contains only the markdown header/table structure.

## Ignore Rules

### `.gitignore`

Added ignore rules for local/runtime files:

- Python cache files
- `.DS_Store`
- `.venv/`
- `.pytest_cache/`
- `usage.json`
- `usage.md`
- `gateway.log`
- sandbox runtime contents, while preserving `sandbox/.gitkeep`

Reason: keep generated/runtime artifacts out of versioned project state.

## Raw Chat Capture Note

### `/Users/aryamanchandak/Documents/AI Code/Database/Raw Data/chats/README.md`

- Added a short README describing raw chat storage.
- Clarified that raw chat capture should be automatic runtime behavior, not an
  MCP tool and not a model-selectable action.
- Stated that every gateway chat request should eventually produce a raw record,
  including failures.

Reason: record the architectural decision without implementing the full capture
pipeline yet.

## Shared Gemini File Handling

### Decisions Captured

- Keep one MCP-facing Gemini Files API upload tool.
- The upload tool accepts only local files already present in the server sandbox.
- Do not support HTTP/HTTPS download-and-upload behavior yet.
- Return both Gemini identifiers:
  - `name`, e.g. `files/...`
  - `uri`, passed to downstream tools as `file_uri`
- Keep raw PDF bytes as a narrow internal path for specific PDF workflows, not as
  a general MCP upload tool.

### `shared/backend_utils.py`

- Added `gemini_api_key()` and `make_gemini_client()` for consistent Gemini
  client setup.
- Added `gemini_file_name(...)` so downstream tools can resolve a Gemini file
  from a full URI, `files/...` name, or bare file id.
- Kept `get_gemini_file(...)` as the lookup helper used by downstream analysis
  tools.
- Added `wait_for_gemini_file_active(...)` for Files API upload polling.
- Added `pdf_bytes_part(...)` as the PDF-only inline bytes helper.
- Removed the older unused `upload_pdf_to_gemini(...)` helper.

### `tools/utility/file_upload/`

- Replaced the old `upload_file(file_path) -> str` registered tool with
  `upload_file_to_gemini(source) -> dict`.
- The tool now returns `name`, `uri`, `mime_type`, and `display_name`.
- The tool rejects HTTP/HTTPS URLs and absolute/local paths outside the sandbox.

### `tools/utility/gemini/`

- Removed the duplicate URL-capable Gemini upload tool package.

### Downstream Tool Docs

- Updated file URI docstrings and READMEs to point callers to the `uri` returned
  by `upload_file_to_gemini`.
- Updated lease deed PDF byte handling to use the shared `pdf_bytes_part(...)`
  helper.

## Utility Web Search

### Decision

- Keep `web_search` as one MCP tool in its own folder.
- Use Brave Search as the only web search provider.
- Do not use Gemini Google Search for this tool.
- Do not use DuckDuckGo fallback for this tool.
- The calling agent chooses `max_results` based on query complexity.
- The tool validates and caps `max_results`; it does not infer complexity.

### `tools/utility/web_search/tool.py`

- Replaced the Gemini REST call and DuckDuckGo fallback with Brave Search.
- Added AI Code root `.env` lookup for `BRAVE_SEARCH_API_KEY`.
- Kept `AI_CODE_ROOT` as an override for moved workspaces.
- Added blank-query validation.
- Raised the tool cap to 20 results.
- Normalized each result to:
  - `title`
  - `url`
  - `snippet`
  - `source`
- Changed usage logging from `duckduckgo` to `brave_search`.
- Updated the MCP-facing docstring with query-shaping guidance:
  - pass a concise search-engine query, not a chatty prompt;
  - use keywords plus context;
  - include entity/topic, important nouns, timeframe, document/event, or metric;
  - for broad research, run multiple focused searches instead of one giant query.

### `tools/utility/web_search/README.md`

- Updated provider documentation to Brave Search.
- Documented that the agent, not the tool, chooses result count from query
  complexity.
- Documented required `BRAVE_SEARCH_API_KEY` configuration.
- Documented how to write relevant search queries.

### AI Agent Decision Prompt

- Added an instruction in the Decision layer telling the agent to choose
  `web_search.max_results` based on query complexity.
- The note lives at:
  `/Users/aryamanchandak/Documents/AI Code/AI Agent/src/agent/cognition/decision.py`

## Utility Fetch

### Decision

- Keep `fetch_url` as one MCP tool in its own folder.
- Keep crawl4ai headless Chromium as the fetch/extraction implementation.
- Treat `fetch_url` as a single-URL fetcher, not a search or relevance-ranking
  tool.
- Add URL validation before browser launch.
- Enforce a hard 30-second maximum timeout.

### `tools/utility/fetch/tool.py`

- Added validation for blank URLs, scheme, hostname, embedded credentials, and
  malformed ports.
- Limited supported schemes to `http://` and `https://`.
- Rejected localhost and literal private/local/reserved/multicast IP URLs.
- Changed the default timeout to 30 seconds.
- Capped caller-provided timeout values to 30 seconds.
- Wrapped crawl4ai execution in `asyncio.wait_for(...)`.
- Raised a clear timeout error when the crawl exceeds the enforced timeout.

### `tools/utility/fetch/README.md`

- Documented that `fetch_url` fetches one explicit URL and does not perform
  discovery or relevance ranking.
- Documented validation rules, timeout behavior, return shape, and cybersecurity
  caveats.

## Utility Markdown Files

### Decision

- Split the former `tools/utility/files/` multi-tool folder into one folder per
  MCP tool.
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
- Focus file creation and editing on sandbox markdown files for now.
- Do not add arbitrary 1 MB read/write caps in this pass.
- Keep binary files and rich document formats such as `.docx` out of these
  tools; those should get dedicated tools later.

### New Tool Folders

- `tools/utility/read_file/`
- `tools/utility/list_dir/`
- `tools/utility/suggest_file_path/`
- `tools/utility/create_folder/`
- `tools/utility/create_file/`
- `tools/utility/append_file/`
- `tools/utility/update_file/`
- `tools/utility/edit_file/`

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
- `suggest_file_path` proposes an unused markdown filename in an existing
  sandbox directory without creating anything.
- `suggest_file_path` does not choose the correct folder; the caller must
  already provide a directory.
- `create_folder` creates one sandbox directory, with optional parent-directory
  creation through `create_parents=True`.
- `append_file` appends UTF-8 text to an existing markdown file, writing a
  separator first when the file already has content.
- `create_file` documentation now explicitly explains the filesystem write path:
  sandbox resolution, markdown suffix check, existence checks, and
  `Path.write_text(content, encoding="utf-8")`.
- `create_file` mechanics were explicitly clarified with the user: the file is
  created by Python's `Path.write_text(content, encoding="utf-8")` call, not by
  MCP, the registry, or sandbox validation.

## Verification Completed

Runtime/usage block:

- Ran Python compile checks for:
  - `mcp_server.py`
  - `tool_registry.py`
  - `usage.py`
- Used `PYTHONPYCACHEPREFIX=/tmp/mcp_server_pycache` so bytecode writes stayed
  inside an allowed temporary path.
- Verified that `usage.bump(...)` can create/write the markdown usage log.

Shared Gemini/file-upload block:

- Compiled the touched Python files with:
  `UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m py_compile ...`
- Verified `gemini_file_name(...)` normalizes all supported reference forms to
  `files/...`.
- Verified `pdf_bytes_part(b"")` raises `ValueError`.
- Verified isolated utility-group registration exposes 10 utility tools and
  includes `upload_file_to_gemini`, with no `upload_file` or `upload_to_gemini`.
- Verified `upload_file_to_gemini("")` and an HTTP URL both raise before any
  upload.

Utility web-search block:

- Compiled `tools/utility/web_search/tool.py`.
- Compiled the AI Agent Decision prompt file.
- Ran an isolated mocked Brave response check for:
  - query trimming
  - `count` request parameter
  - API key header
  - result normalization
  - blank-query rejection
- Verified `.env` lookup through `AI_CODE_ROOT`.

Utility fetch block:

- Compiled `tools/utility/fetch/tool.py`.
- Ran isolated checks for:
  - URL trimming
  - blank URL rejection
  - non-http(s) URL rejection
  - embedded credential rejection
  - malformed port rejection
  - localhost and literal private IP URL rejection
  - timeout capping
  - `fetch_url(...)` timeout enforcement without launching a browser

Utility markdown-files block:

- Compiled `sandbox.py`, the five split markdown file tool modules, and the
  three added file-workflow tool modules.
- Ran isolated checks for:
  - utility registration of the eight markdown/file workflow tool names
  - markdown extension enforcement
  - sandbox traversal rejection
  - suggest path/create folder/create/read/append/update/edit/list behavior
  - empty `find` rejection
  - non-markdown write rejection

## Current Caveats

- Full `import tools` remains blocked in this local sandbox by the known
  knowledge-memory external import path issue: the sibling `agent/` dependency
  expected by `mcp_server.py` is not available on the current `PYTHONPATH` in
  this harness, causing `tools/knowledge/memory/tool.py` to fail on
  `import memory`.
- `ddgs` is now unused by `tools/utility/web_search/`, but still appears in
  `pyproject.toml` and `uv.lock`. Dependency cleanup was intentionally left for
  a separate explicit pass.
- `tools/utility/file_upload/`, `shared/backend_utils.py`, and Gemini upload
  behavior need a focused future review before broader cleanup.
- `fetch_url` does not yet enforce a domain allowlist, perform DNS-based private
  network blocking, inspect redirect chains before browser navigation, or scan
  fetched content for malware/phishing risk.
- Markdown file tools do not impose a hard content-size cap yet. Very large
  markdown content may still hit MCP, client, or model context limits.
- Future TODOs are consolidated in root `TODO.md`.
- File/directory intelligence is a future architecture item, captured in root
  `TODO.md`. Current tools do not maintain a
  directory graph, use watchdog, classify folder purpose, communicate global
  filesystem context to the model, or automatically choose where a new document
  belongs.

## Suggested Next Chat Starting Point

Continue the one-tool-at-a-time review of `tools/utility/`.

Recommended next tool:

- Continue the file-workflow tools one at a time. `create_file` has been
  approved after explaining the exact creation point. Next likely tools:
  `suggest_file_path`, `create_folder`, `append_file`, `read_file`,
  `update_file`, `edit_file`, and `list_dir`.

Alternative if the user wants to tackle the more complex area first:

- review `shared/backend_utils.py` plus `tools/utility/file_upload/` together,
  because provider file upload is more complex than the folder name suggests.
