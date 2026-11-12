# Absorption Seam Test — Phase 1.x (Post-1.4)

## Context

All Phase 1 stages are complete:
- 1.0: Scaffold + contracts + meter ✓
- 1.1: Source clients + storage + dedup ✓  
- 1.2: Two-axis triage + expansion ✓
- 1.3: Annotation + synthesis + citation gate + research_topic E2E ✓
- 1.4: verify_claims + surface-only output ✓

The spec requires an **absorption seam test** — a dry-run verification that the package can be relocated into a parent monorepo (`core/aggregator/research-mcp/`) without breaking imports, paths, or config. This is a **test-only validation task** — no production files move.

Project root: `/Users/aryamanchandak/Documents/AI OS/Research_MCP/`

---

## What needs to be written

**File:** `tests/test_absorption_seam.py`

This test verifies the package is structured such that it COULD be moved to a new path. It does this by:

1. Copying the entire `src/research_mcp/` package to a temp directory
2. Patching `sys.path` to point at the temp location
3. Verifying all modules import cleanly from the new path
4. Verifying that environment variable config (`RESEARCH_MCP_DB_PATH`, `RESEARCH_MCP_TRUSTED_SOURCES_PATH`) would override hardcoded paths
5. Verifying the MCP server module loads from the new path

**Also produce:** `ABSORPTION_SEAM_CHECKLIST.md` in the project root — a short markdown checklist documenting the actual steps needed for a real move (what env vars to set, what config to update, what paths change). This is the "one-checklist diff for Phase 2" the spec requires.

---

## Test details

### `tests/test_absorption_seam.py`

```python
# Mirror style of existing phase tests (no pytest-asyncio, tempdir pattern)
```

**Test 1 — `test_package_imports_from_new_path`**:
- Copy `src/research_mcp/` to `tmp_dir/research_mcp/`
- Insert `tmp_dir` at front of `sys.path` (and remove the real `src/` path)
- Import `research_mcp.contracts`, `research_mcp.engine`, `research_mcp.server` — assert no ImportError
- Restore `sys.path` after

**Test 2 — `test_db_path_from_env_var`**:
- Set `RESEARCH_MCP_DB_PATH` env var to a tempfile path
- Import `research_mcp.database` (fresh import via `importlib.reload`)  
- Call `init_db` with the env-var path
- Assert DB file created at that path (not the default `data/research.db`)
- Unset the env var after

**Test 3 — `test_trusted_sources_path_from_env_var`**:
- Set `RESEARCH_MCP_TRUSTED_SOURCES_PATH` env var to point to a copy of `trusted_sources.yaml` in a tempdir
- Import `research_mcp.trusted_sources` and call `load_trusted_sources()`
- Assert it loads from the env-var path (not the default path in project root)
- Unset the env var after

**Test 4 — `test_server_module_loads`**:
- Import `research_mcp.server` and assert it has a `mcp` attribute (the FastMCP instance)
- Assert the MCP server has the expected tool names registered: `research_topic`, `get_run_status`, `get_run_result`, `verify_claims`, `search_semantic_scholar`, `search_arxiv`, `search_brave`, `search_wikipedia`, `search_google_books`

### Skip condition

Only skip if an API key is needed — Tests 1, 2, 3, 4 are **all pure import/config tests** and do NOT require `ANTHROPIC_API_KEY`. No skip decorator needed.

---

## ABSORPTION_SEAM_CHECKLIST.md

Write a short markdown checklist at the project root documenting:
1. What files move (the `src/research_mcp/` package directory)
2. What env vars to set at the new location (`RESEARCH_MCP_DB_PATH`, `RESEARCH_MCP_TRUSTED_SOURCES_PATH`)
3. What `pyproject.toml` changes are needed (entry point, package name)
4. How to verify after the move (the same `pytest tests/test_absorption_seam.py`)
5. What does NOT need to change (the MCP tools, contracts, prompts structure)

---

## Hard constraints

1. Do NOT modify any existing source files — only create `tests/test_absorption_seam.py` and `ABSORPTION_SEAM_CHECKLIST.md`
2. Use the same test style as `tests/test_phase_1_3.py` (no pytest-asyncio, sync helpers calling `asyncio.get_event_loop().run_until_complete`)
3. Tests must pass without `ANTHROPIC_API_KEY` set
4. `sys.path` must be restored after manipulation (use try/finally)
5. All env vars must be cleaned up after each test (use try/finally or monkeypatch if available)
