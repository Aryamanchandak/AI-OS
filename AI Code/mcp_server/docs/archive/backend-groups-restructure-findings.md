> **HISTORICAL — SUPERSEDED (2026-07-05).** This describes the earlier
> `backend/` (logic) + `groups/` (wiring) mirrored-tree design, which was
> completed and then replaced by the single `tools/` per-tool-folder structure.
> See `../ARCHITECTURE.md` and `../MIGRATION_LOG.md` for the current system.

# Restructure Findings

## Phase 0 - Verify before touching anything

Status: completed.

- `mcp_server/research_tools/` was missing, and `python3 -c "import mcp_server"` failed with `FileNotFoundError` while bootstrapping `research_tools/__init__.py`.
- No other `research_tools` package exists in the workspace.
- Resolution: added a local compatibility package at `mcp_server/research_tools/`. The five research tools remain registered, but their clients raise `SourceUnavailableError`, so calls return the existing structured JSON `source_unavailable` response until the real vendored backend is restored.
- The sibling `agent/` dependency exists at `<repo>/agent`. `mcp_server/mcp_server.py` imports it for `memory.py`, `vector_index.py`, `schemas.py`, `gateway.py`, and `artifacts.py`, which are used by `groups/knowledge/memory_tools.py`.

Next steps:

- Restore the real `research_tools` implementation if live arXiv, Semantic Scholar, Wikipedia, Gemini web, and Google Books search behavior is required.
- Keep the sibling `agent/` path intact through later renames; the knowledge tools depend on it.

Smoke test:

- `python3` fails because the global interpreter has no `mcp` package.
- `Docs/.venv/bin/python -c "import sys; sys.path.insert(0, 'mcp_server'); import mcp_server"` succeeds and reports 38 tools across 7 groups.

## Phase 1 - Migrate the two legacy-shim files

Status: completed.

- `backend/credit_one_pager_mcp.py` and `backend/lease_deed_mcp.py` no longer import `mcp_server.mcp`.
- Removed `@mcp.tool()` decorators from those two backend modules.
- `groups/finance/credit_one_pager.py` and `groups/finance/lease_deed.py` now register the imported functions with `tool_registry.register(group="finance")`.
- Removed the `sys.modules["mcp_server"]` shim and the shim collision guard from `mcp_server.py`.
- Smoke test passed with `Docs/.venv/bin/python`.
- `list_tools()` shows the same callable tool set. Startup now reports 42 registry tools because `generate_credit_one_pager`, `build_rent_roll`, `build_clause_report`, and `process_lease_deed` moved from direct FastMCP shim registration into `tool_registry`.

Next steps:

- Phase 2: rename `backend/tools/` to `backend/shared/`, rename top-level `tools/` to `groups/`, and simplify group import bootstrapping.

## Phase 2 - Resolve the `tools` package name collision

Status: completed.

- Moved `backend/tools/shared/` to `backend/shared/`.
- Updated backend imports to `from shared.backend_utils import get_gemini_file`.
- Renamed `mcp_server/tools/` to `mcp_server/groups/`.
- Simplified `mcp_server.py` to import `groups` normally, with `_ROOT` inserted into `sys.path`.
- Smoke test passed with `Docs/.venv/bin/python`; `list_tools()` still reports the same groups and tools.
- `mcp_server/tools/` no longer exists. `mcp_server/backend/tools/` remains only because generated cache files block removing the directory; this is recorded for Phase 6 cleanup.

Next steps:

- Phase 3: move flat backend modules into domain folders that mirror `groups/`, then update all group wiring imports.

## Phase 3 - Reorganize `backend/` to mirror `groups/`

Status: completed.

- Created backend domain folders: `documents/`, `finance/`, `media/`, `news/`, and `utility/`.
- Moved flat backend modules into domain folders and removed the `_mcp` suffix from their filenames.
- Renamed backend prompt-template file `podcast.py` to `media/podcast_prompts.py`.
- Updated group wiring imports to use the new backend domain module paths.
- Smoke test passed with `Docs/.venv/bin/python`; `list_tools()` still reports the same groups and tools.

Next steps:

- Phase 4: move `upload_file` from `documents` to `utility`, and move meeting-recorder tools from `documents` to `media`.

## Phase 4 - Re-home mis-grouped tools

Status: completed.

- Moved `groups/documents/file_upload.py` to `groups/utility/file_upload.py`.
- Changed `upload_file` registration from `documents` to `utility`.
- Moved `groups/documents/meeting_recorder.py` to `groups/media/meeting_recorder.py`.
- Changed meeting-recorder tool registrations from `documents` to `media`.
- Updated group `__init__.py` imports so the moved wiring files load from their new groups.
- Smoke test passed with `Docs/.venv/bin/python`.
- Intentional group changes confirmed: `upload_file` is now under `utility`; `transcribe_audio`, `summarize_meeting`, `process_meeting_audio`, and `chat_with_meeting` are now under `media`.

Next steps:

- Phase 5: add a runtime dependency manifest pinned from the working `Docs/.venv` environment.

## Phase 5 - Dependency manifest

Status: completed.

- Scanned direct imports in `mcp_server/` and the sibling `agent/` modules loaded by knowledge tools.
- Added `mcp_server/pyproject.toml` with runtime dependencies pinned from `Docs/.venv` where installed.
- Included sibling-agent runtime requirements needed at MCP startup for knowledge tools: `faiss-cpu`, `numpy`, and `pydantic`.
- `crawl4ai` is required by `groups/utility/fetch.py` but is not installed in `Docs/.venv`, so it is listed unpinned.
- Did not include `tenacity` because it is installed but not imported by this codebase.
- `mcp_server/pyproject.toml` parses successfully.
- Smoke test passed with `Docs/.venv/bin/python`.

Next steps:

- Phase 6: add ignore rules and remove generated/cache files.

## Phase 6 - Repo hygiene

Status: completed.

- Added root `.gitignore` covering Python caches, `.DS_Store`, `usage.json`, and `sandbox/*` while preserving `sandbox/.gitkeep`.
- Removed generated `__pycache__`, `*.pyc`, and `.DS_Store` files from the project.
- Removed the stale `mcp_server/backend/tools/` directory after Phase 2 moved its only source package to `backend/shared/`.
- No Git repository is initialized at the workspace root, so no commit was created.
- Note: the cleanup command also removed Python bytecode caches under `Docs/.venv`; import smoke passed afterward, and those caches are regenerated automatically.

Next steps:

- Phase 7: archive the stale original design doc and write current architecture documentation.

## Phase 7 - Documentation

Status: completed.

- Moved `docs/Plan.md` to `docs/archive/original-design-plan.md`.
- Added a historical note marking the archived plan as superseded.
- Added `docs/ARCHITECTURE.md` describing the current entry point, registry pattern, `groups/` to `backend/` layout, sibling `agent/` dependency, and `research_tools` compatibility package.
- Smoke test passed with `Docs/.venv/bin/python`.

## Phase 8 - Smoke test

Status: completed for import and tool listing.

- Final command run: `Docs/.venv/bin/python -c "import sys; sys.path.insert(0, 'mcp_server'); import mcp_server; print(mcp_server.list_tools())"`.
- Result: import succeeded and `list_tools()` reported 42 registry tools across 7 groups.
- `--dev` MCP Inspector launch was not run because it starts an interactive `npx @modelcontextprotocol/inspector` process.
- Project bytecode caches were removed again after the final smoke run.

Remaining follow-ups:

- Restore the real `research_tools` implementation if live research search is required.
- Install `crawl4ai` before using `fetch_url`; it is declared in `mcp_server/pyproject.toml` but was missing from `Docs/.venv`.
- Initialize Git if this workspace should track the restructure as a commit history.
