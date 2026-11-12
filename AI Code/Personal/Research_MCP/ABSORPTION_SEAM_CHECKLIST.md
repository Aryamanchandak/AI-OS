# Absorption Seam Checklist — Moving research-mcp into a Parent Monorepo

Use this checklist when physically relocating the package to a new path such as
`core/aggregator/research-mcp/` inside a parent monorepo.

---

## 1. Files and directories that move

- [ ] `src/research_mcp/` — the entire Python package directory (copy verbatim)
- [ ] `trusted_sources.yaml` — domain-allowlist config (copy to the new repo root or a config/ dir)
- [ ] `pyproject.toml` — update before moving (see section 3)
- [ ] `prompts/` — all prompt text files used by annotation, synthesis, expansion, triage
- [ ] `data/` — SQLite database (`research.db`) if you want to carry historical runs across
- [ ] `runs/` — essay output directory (optional; re-created automatically on first run)
- [ ] `audit/` — JSONL audit logs (optional; carry if audit continuity matters)

---

## 2. Environment variables to set at the new location

Set these in the new repo's `.env`, `docker-compose.yml`, or CI secrets:

| Variable | Purpose | Example value |
|---|---|---|
| `RESEARCH_MCP_DB_PATH` | Absolute path to the SQLite database | `/app/data/research.db` |
| `RESEARCH_MCP_TRUSTED_SOURCES_PATH` | Absolute path to `trusted_sources.yaml` | `/app/config/trusted_sources.yaml` |
| `ANTHROPIC_API_KEY` | Claude API key (required for live runs) | `sk-ant-...` |
| `BRAVE_API_KEY` | Brave Search key (optional; Brave tool degrades gracefully without it) | `BSAx...` |
| `GOOGLE_BOOKS_API_KEY` | Google Books key (optional; tool degrades gracefully) | `AIza...` |

> **Why env vars are sufficient:** `server.py` reads `RESEARCH_MCP_DB_PATH` at import
> time; `trusted_sources.py` reads `RESEARCH_MCP_TRUSTED_SOURCES_PATH` in
> `load_trusted_sources()`. No hardcoded absolute paths remain in production code after
> these two vars are set.

---

## 3. pyproject.toml changes required

- [ ] Update `[project] name` if the monorepo uses a scoped package name (e.g. `core-research-mcp`)
- [ ] Update `[project.scripts]` entry point if the CLI command name changes:
  ```toml
  [project.scripts]
  research-mcp = "research_mcp.server:main"
  ```
- [ ] Update `[tool.hatch.build.targets.wheel] packages` to reflect the new source tree root:
  ```toml
  packages = ["src/research_mcp"]   # adjust if src/ layout changes
  ```
- [ ] Add the new package as a workspace member in the monorepo's root `pyproject.toml`
  (exact syntax depends on the monorepo tool: `uv`, `poetry`, `hatch`, etc.)
- [ ] Confirm `requires-python = ">=3.11"` is compatible with the monorepo's Python constraint

---

## 4. How to verify after the move

Run the absorption seam test suite from the new location:

```bash
pytest tests/test_absorption_seam.py -v
```

All 4 tests must pass without `ANTHROPIC_API_KEY` set. They validate:

1. **`test_package_imports_from_new_path`** — package imports cleanly when `sys.path`
   points at the relocated directory (no hardcoded relative imports that break on move)
2. **`test_db_path_from_env_var`** — `RESEARCH_MCP_DB_PATH` correctly redirects the
   database away from the default `data/research.db`
3. **`test_trusted_sources_path_from_env_var`** — `RESEARCH_MCP_TRUSTED_SOURCES_PATH`
   correctly redirects config away from the default project-root `trusted_sources.yaml`
4. **`test_server_module_loads`** — `research_mcp.server.mcp` exists and all 9 MCP tools
   are registered

For a full integration check after the move, run the Phase 1.3 / 1.4 test suites with
a live `ANTHROPIC_API_KEY`:

```bash
pytest tests/test_phase_1_3.py tests/test_phase_1_4.py -v
```

---

## 5. What does NOT need to change

- [ ] The MCP tool names (`research_topic`, `get_run_status`, `get_run_result`,
  `verify_claims`, `search_*`) — clients using these tools require no update
- [ ] The contracts (`LogicalSource`, `RunRecord`, `ResearchResult`, `BriefReview`) —
  the Pydantic schema is stable
- [ ] The prompts structure in `prompts/` — filenames and content are unchanged
- [ ] The citation gate logic (`citation_gate.py`) — pure in-process logic, no path deps
- [ ] The dedup fingerprinting logic (`dedup.py`) — pure in-process logic
- [ ] The triage / expansion / annotation / synthesis pipeline — all path-independent
- [ ] The SQLite schema — `init_db()` is idempotent; existing DBs migrate forward
- [ ] Any MCP client configuration pointing at this server — the transport (`stdio`) and
  tool signatures are unchanged
