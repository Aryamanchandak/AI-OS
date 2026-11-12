> **HISTORICAL — SUPERSEDED (2026-07-05).** This describes the earlier
> `backend/` (logic) + `groups/` (wiring) mirrored-tree design, which was
> completed and then replaced by the single `tools/` per-tool-folder structure.
> See `../ARCHITECTURE.md` and `../MIGRATION_LOG.md` for the current system.

# mcp_server Restructure Plan

Execute in order. Each phase should leave the server runnable — verify with the smoke test in Phase 8 after every phase, not just at the end.

## Phase 0 — Verify before touching anything

1. Check whether `research_tools/` actually exists somewhere reachable. `mcp_server.py` bootstraps it from `os.path.join(_ROOT, "research_tools")` (i.e. `mcp_server/research_tools/`), but it is **not present** in the current tree. Either:
   - it's missing and `tools/research/` is currently dead/broken code, or
   - it was meant to be vendored in and never was.
   Resolve this first — if it's genuinely missing, decide whether to stub it out, remove `tools/research/` entirely, or get the real package from wherever it lives before proceeding.
2. Confirm the sibling `agent/` dependency. `mcp_server.py` does `sys.path.insert(0, os.path.join(os.path.dirname(_ROOT), "agent"))` to pull in `memory.py`, `vector_index.py`, `schemas.py`, `gateway.py`, `artifacts.py` for `tools/knowledge/memory_tools.py`. This reaches *outside* the `mcp_server` folder into a sibling project. Confirm that folder exists at `<parent>/agent` and document the dependency — do not break this path during the rename in Phase 3.

## Phase 1 — Migrate the two legacy-shim files

`backend/credit_one_pager_mcp.py` and `backend/lease_deed_mcp.py` currently do `from mcp_server import mcp` and decorate their functions with `@mcp.tool()` directly, instead of going through `tool_registry.register()` like every other tool. This requires `mcp_server.py` to maintain a shim (`sys.modules.setdefault("mcp_server", ...)`) and a manual name-collision guard just for these two files.

1. In both files, replace the `from mcp_server import mcp` / `@mcp.tool()` pattern with the same pattern used elsewhere: keep the functions undecorated, and register them from the corresponding `tools/finance/*.py` wiring file via `register(group="finance")(fn)`.
2. In `mcp_server.py`, delete:
   - the `sys.modules.setdefault("mcp_server", sys.modules[__name__])` shim line and its comment,
   - the `_shim_names` collision-guard block.
3. Update `tools/finance/credit_one_pager.py` and `tools/finance/lease_deed.py` to register the imported functions explicitly (matching the style already used in `tools/finance/credit_note_eval.py`).
4. Smoke test (Phase 8).

## Phase 2 — Resolve the `tools` package name collision

There are currently two unrelated packages both importable as `tools`:
- `mcp_server/tools/` — the wiring/registration layer, secretly loaded into `sys.modules["groups"]`.
- `backend/tools/shared/backend_utils.py` — a shared-utilities package, which `backend/*.py` files import as `from tools.shared.backend_utils import get_gemini_file`. This only resolves correctly today because `backend/` is inserted into `sys.path` *before* the root, so it shadows the real `tools/` package. This shadowing is called out as a known hazard in a comment in `mcp_server.py`.

Steps:
1. Rename `backend/tools/` → `backend/shared/` (so `backend/shared/backend_utils.py`).
2. Update the four import sites that reference it:
   - `backend/credit_note_eval_mcp.py`
   - `backend/credit_one_pager_mcp.py`
   - `backend/ara_mcp.py`
   - `backend/meeting_recorder_mcp.py`
   Change `from tools.shared.backend_utils import get_gemini_file` → `from shared.backend_utils import get_gemini_file` (or use the explicit path resulting from Phase 4's restructuring — see note in Phase 4).
3. Rename the top-level `mcp_server/tools/` → `mcp_server/groups/` (it is already loaded under this name at runtime; this makes the on-disk name match reality).
   - Update `groups/__init__.py` (was `tools/__init__.py`) — no change needed to its internal `importlib.import_module(f"groups.{name}")` logic, since the package is now actually named `groups`.
   - In `mcp_server.py`, simplify the bootstrap: since the directory is now genuinely named `groups`, you may be able to replace the manual `importlib.util.spec_from_file_location("groups", ...)` dance with a normal `import groups`, provided `_ROOT` is on `sys.path`. Try the simple form first; fall back to the existing explicit-loader approach only if it's needed for some reason (e.g. running as a script without `_ROOT` on `sys.path`).
4. Smoke test (Phase 8).

## Phase 3 — Reorganize `backend/` to mirror `groups/`

`backend/` is currently 11 flat files with no domain structure, while `groups/` (formerly `tools/`) is already split into `documents/`, `finance/`, `knowledge/`, `media/`, `news/`, `research/`, `utility/`. Mirror that structure inside `backend/` and drop the misleading `_mcp` suffix (most of these files contain no MCP code at all — only the two files fixed in Phase 1 ever did).

Target layout:

```
backend/
├── documents/
│   ├── ara.py                  # was ara_mcp.py
│   └── meeting_recorder.py     # was meeting_recorder_mcp.py
├── finance/
│   ├── credit_note_eval.py     # was credit_note_eval_mcp.py
│   ├── credit_one_pager.py     # was credit_one_pager_mcp.py
│   └── lease_deed.py           # was lease_deed_mcp.py
├── media/
│   ├── image_gen.py            # was image_gen_mcp.py
│   ├── podcast.py              # was podcast_mcp.py
│   ├── podcast_prompts.py      # was podcast.py (rename — these are prompt templates, not a tool module)
│   └── youtube_intelligence.py # was youtube_intelligence_mcp.py
├── news/
│   └── market_brief.py         # was market_brief_mcp.py
├── utility/
│   └── file_upload.py          # was file_upload_mcp.py
└── shared/
    └── backend_utils.py        # from Phase 2
```

Steps:
1. Create the subfolders and `git mv` (or plain move) each file per the mapping above.
2. Update every import across the repo that references the old flat module paths — these live in the corresponding `groups/*/*.py` wiring files:
   - `groups/documents/annual_report.py` → `from documents.ara import analyze_annual_report`
   - `groups/documents/file_upload.py` → move its registration into `groups/utility/` (see Phase 5) and import from `utility.file_upload`
   - `groups/documents/meeting_recorder.py` → `from documents.meeting_recorder import ...`
   - `groups/finance/credit_note_eval.py` → `from finance.credit_note_eval import ...`
   - `groups/finance/credit_one_pager.py` / `lease_deed.py` → updated already in Phase 1, adjust path to `finance.credit_one_pager` / `finance.lease_deed`
   - `groups/media/image_gen.py` → `from media.image_gen import generate_image`
   - `groups/media/podcast.py` → `from media.podcast import ...`
   - `groups/media/youtube.py` → `from media.youtube_intelligence import ...`
   - `groups/news/market_brief.py` → `from news.market_brief import ...`
3. Update the four `backend_utils` import sites from Phase 2 to use their new relative location (e.g. `from shared.backend_utils import get_gemini_file`, assuming `backend/` stays on `sys.path` as the import root — confirm against how `mcp_server.py` sets up `sys.path.insert(0, os.path.join(_ROOT, "backend"))`).
4. Inside `backend/media/podcast.py` (formerly `podcast_mcp.py`), update its import of the prompt templates to `from media.podcast_prompts import ...` (formerly `from podcast import ...` / inline).
5. Smoke test (Phase 8).

## Phase 4 — Re-home mis-grouped tools

1. `upload_file` (now `utility/file_upload.py` per Phase 3) is currently registered under `group="documents"` in `groups/documents/file_upload.py`. Move the wiring file to `groups/utility/file_upload.py` and register under `group="utility"`. Update `groups/utility/__init__.py` to import it; remove it from `groups/documents/__init__.py`.
2. `meeting_recorder`'s four tools (`transcribe_audio`, `summarize_meeting`, `process_meeting_audio`, `chat_with_meeting`) are registered under `group="documents"` in `groups/documents/meeting_recorder.py`. Move the wiring file to `groups/media/meeting_recorder.py` and register under `group="media"`. Update `groups/media/__init__.py` and `groups/documents/__init__.py` accordingly.
3. Smoke test (Phase 8).

## Phase 5 — Dependency manifest

1. Add `mcp_server/pyproject.toml` (or `requirements.txt` if that fits the existing `uv`/`.venv` workflow better — `.claude/settings.local.json` shows `uv` commands already in use) listing the actual runtime dependencies observed in the code: `mcp`, `google-genai` (or `google-generativeai`, check which is actually imported), `httpx`, `crawl4ai`, `python-docx`, `openpyxl`, `tenacity`, plus anything else found via a dependency scan.
2. Pin versions from whatever is currently installed in `../.venv` so the manifest reflects what's actually working today, not guesses.

## Phase 6 — Repo hygiene

1. Add a `.gitignore` covering `__pycache__/`, `*.pyc`, `.DS_Store`, `usage.json`, `sandbox/*` (keep `sandbox/.gitkeep` if the folder itself should persist).
2. Delete existing `.DS_Store` files (root, `backend/`, `tools/`/`groups/`) and `__pycache__` directories.
3. If not already version-controlled, consider `git init` + initial commit at this point, after the structure is stable — makes every subsequent phase revertible.

## Phase 7 — Documentation

1. `docs/Plan.md` describes a design that was never built (a `config.py`/`server.py` split, `tools/document/`/`tools/market/` layout, a 23-tool composite/component model). It no longer matches reality and will mislead anyone reading it.
2. Move it to `docs/archive/original-design-plan.md` with a one-line header noting it's historical and superseded.
3. Write a new `docs/ARCHITECTURE.md` describing the system as it actually exists post-restructure: the `tool_registry.register(group=...)` pattern, the `groups/` ↔ `backend/` domain mirroring, the `agent/` sibling-folder dependency for knowledge tools, and the `research_tools/` situation resolved in Phase 0.

## Phase 8 — Smoke test (run after every phase)

```bash
cd mcp_server
../.venv/bin/python -c "import mcp_server"   # or "import server" if entry point renamed
../.venv/bin/python mcp_server.py --dev      # opens MCP Inspector if available; Ctrl+C once it starts cleanly
```

Confirm:
- No import errors.
- `list_tools()` (callable from the Inspector, or by adding a temporary `print(list_tools())` call) reports the same total tool count and group names as before the phase's changes, except for the intentional moves in Phase 4 (group reassignments) and Phase 1 (collision-guard removal shouldn't change the count).

## Optional follow-up — rename the entry point

`mcp_server.py` sharing its name with the package one level up (`mcp_server/`) is mildly confusing but not broken. If desired, rename it to `server.py` once Phases 1–4 are done and stable, updating any external launch scripts / Claude Desktop config that reference `mcp_server.py` by path.
