# Per-Tool Folder Restructure Plan

> ✅ **COMPLETED 2026-07-05.** Executed to a single `tools/` root, one folder per
> tool; 62 tools / 10 groups preserved exactly. See `MIGRATION_LOG.md` for the
> old→new mapping and `ARCHITECTURE.md` for the resulting system. This file is kept
> as the record of intent.

**Goal:** Kill the `backend/` ↔ `groups/` mirrored-tree split (and the scattered
`Podcast MCP tools/` subsystem) by collapsing everything into a **single `tools/`
root where each tool is its own folder**. Open one folder → see the whole tool:
its registration, its logic, its prompts, its contracts. No piece of a tool lives
in another tree anymore.

This **supersedes** the completed `../RESTRUCTURE_PLAN.md` (which established the
`backend/`+`groups/` domain mirroring — we are now merging those two trees).

> Written for Codex to implement. Each phase must leave the server runnable —
> run the smoke test (Phase 9) after **every** phase, not just at the end.

---

## ⚠️ EXTERNAL TODOs (outside `mcp_server/` — for tracking only, do NOT act on these)

These are dependencies that live in *other* directories. Do not modify them.
Just preserve the wiring and note it in `docs/ARCHITECTURE.md`.

1. **Sibling `agent/` folder** — `mcp_server.py` does
   `sys.path.insert(0, os.path.join(os.path.dirname(_ROOT), "agent"))` so that the
   knowledge memory tool can `import memory / vector_index / schemas / gateway /
   artifacts`. This restructure must **keep that path insert unchanged**. The
   `agent/` folder itself is out of scope.
2. **Launch config** — anything outside this repo that launches the server by path
   (Claude Desktop config, shell aliases, cron) references `mcp_server.py`. We are
   **not** renaming the entry point, so no external change is required — but if you
   ever rename it, that config must be updated. Flagged for awareness only.

---

## The one hard invariant (do not break this during co-location)

The reason `backend/` existed was **pure logic importable without booting MCP**.
Co-locating files into one folder makes it easy to silently re-tangle that. The rule:

- **`logic.py` imports NOTHING from `tool_registry`, `mcp`/FastMCP, or its own
  package's `tool.py`/`__init__.py`.** It is plain Python.
- Dependencies flow **one direction**: `tool.py → logic.py → prompts.py/contracts.py`.
  Never the reverse.
- Test = `import tools.<group>.<tool>.logic` with zero registration side effects.

Cleanup while you're here: several `backend/*` modules currently
`from mcp.server.fastmcp import FastMCP` but never use it
(`credit_note_eval.py`, `image_gen.py`, `ara.py`, `meeting_recorder.py`,
`market_brief.py`). Drop those dead imports as each moves to `logic.py`.

---

## Target layout

```
mcp_server/
├── mcp_server.py            # entry point (unchanged name)
├── tool_registry.py         # unchanged
├── usage.py, sandbox.py     # unchanged
├── shared/                  # cross-group shared code (was backend/shared/)
│   └── backend_utils.py
└── tools/                   # THE single tool root (was groups/ + backend/)
    ├── __init__.py          # auto-discovers each <group> subpackage
    └── <group>/
        ├── __init__.py      # auto-discovers each tool subpackage in this group
        ├── _shared/         # group-level shared code — ONLY if >1 tool needs it
        └── <tool>/          # ← one folder per tool (or per coupled feature)
            ├── __init__.py  # register(group="<group>")(fn) for each tool fn
            ├── tool.py      # MCP-facing wrappers; docstrings ARE the MCP schema
            ├── logic.py     # pure logic (was backend/<group>/<tool>.py)
            ├── prompts.py   # prompt templates          (only if the tool has any)
            ├── contracts.py # pydantic models / types   (only if the tool has any)
            └── README.md    # what this tool does, its inputs/outputs, its config
```

### File-convention rules

- **Create only the files a tool actually has.** Do NOT manufacture empty
  `contracts.py` / `prompts.py` for symmetry — that is just a new flavor of clutter.
  Today: `lease_deed` has big prompts → `prompts.py`; `market_brief` has pydantic
  models → `contracts.py`; most tools have neither.
- **Tiny inline tools** (utility ones defined directly in the group file with a
  `@register` decorator and no `backend/` counterpart) may keep logic inside
  `tool.py` — no separate `logic.py` needed until it's worth splitting.
- **Auto-discovery is now 3 levels** via `pkgutil` (root → group → tool). Verify the
  chain: `tools/__init__.py` imports each group; `tools/<group>/__init__.py` imports
  each tool subpackage; `tools/<group>/<tool>/__init__.py` calls `register(...)`.

### Granularity for THIS pass (per owner's decision)

**Coupling defines the folder now.** Independent tools get their own folder.
Tightly-coupled tools that cross-import or share a store live together in **one
feature folder** (they will be split into one-tool-per-folder later by the owner —
not in this pass). Concretely, keep-together clusters: the podcast/youtube pipeline
(shared SQLite store + contracts + ingestion bridge), the research search tools
(shared source clients), and multi-tool utility modules (`files`, `utils`).

---

## Full migration mapping (current → new)

| Group | Tool folder | From (wiring) | From (logic) | Extra files |
|---|---|---|---|---|
| finance | `credit_note_eval` | groups/finance/credit_note_eval.py | backend/finance/credit_note_eval.py | — |
| finance | `credit_one_pager` | groups/finance/credit_one_pager.py | backend/finance/credit_one_pager.py | — |
| finance | `lease_deed` | groups/finance/lease_deed.py | backend/finance/lease_deed.py | `prompts.py` (extract inline prompts) |
| documents | `annual_report` | groups/documents/annual_report.py | backend/documents/ara.py | `prompts.py` if prompts inline |
| media | `youtube` | groups/media/youtube.py | backend/media/youtube_intelligence.py | — |
| media | `image_gen` | groups/media/image_gen.py | backend/media/image_gen.py | — |
| media | `podcast` | groups/media/podcast.py | backend/media/podcast.py | `prompts.py` ← backend/media/podcast_prompts.py |
| media | `meeting_recorder` | groups/media/meeting_recorder.py | backend/documents/meeting_recorder.py | (moves out of documents/ — registered under media) |
| media | `podcast_pipeline` (feature folder) | groups/media/podcast_ingestion.py | backend/media/podcast_ingestion.py + podcast_deliver.py | `_pipeline_core/` (see below) |
| media | `_pipeline_core/` (group `_shared`) | — | **all of `Podcast MCP tools/`** + `mcp_tools/` shim | storage/, contracts, ingestion/bridge.py, backup.py, automation/, claims/ |
| news | `market_brief` | groups/news/market_brief.py | backend/news/market_brief.py | `contracts.py` (has pydantic models) |
| knowledge | `memory` | groups/knowledge/memory_tools.py | (logic is inline + sibling `agent/`) | ⚠️ external `agent/` dep |
| knowledge_graph | `graph` (feature folder, 5 tools) | groups/knowledge_graph/tools.py | backend/knowledge_graph/tools.py | — |
| vector_db | `search` (feature folder, 2 tools) | groups/vector_db/tools.py | backend/vector_db/tools.py | — |
| raw_data | `capture` (feature folder, 2 tools) | groups/raw_data/tools.py | backend/raw_data/tools.py | — |
| research | `search` (feature folder, 5 tools) | groups/research/search.py + clients.py | research_tools/ (sources/, contracts.py) | `sources/`, `clients.py`, `contracts.py` |
| utility | `web_search` | groups/utility/web_search.py | (inline) | — |
| utility | `fetch` | groups/utility/fetch.py | (inline) | — |
| utility | `files` (feature folder, 5 tools) | groups/utility/files.py | (inline) | — |
| utility | `misc` (feature folder, 2 tools) | groups/utility/utils.py | (inline) | — |
| utility | `gemini` | groups/utility/gemini.py | (inline) | — |
| utility | `file_upload` | groups/utility/file_upload.py | backend/utility/file_upload.py | — |
| — | `shared/backend_utils.py` | — | backend/shared/backend_utils.py | root-level, imported as `from shared.backend_utils import ...` |

**`Podcast MCP tools/` fold-in detail** (owner confirmed: fully in scope, break as needed):
Its contents — `ingestion/bridge.py`, `backup.py`, `storage/{client,contracts}.py`,
`contracts/episode.py`, `shared/contracts.py`, `claims/{contracts,extraction,verification}`,
`automation/workflows.py`, and the scaffold `tools/{research,summarise,transcribe}.py` —
are the **shared podcast-pipeline core**. Land them under
`tools/media/_pipeline_core/` (a group-level `_shared`). The scaffold tools become
proper tool folders `tools/media/{transcribe,summarise,research}/` **as stubs** — keep
them registered/importable, and give each a `tool.py` with a **detailed intent comment**
explaining what it should do once its dependency (LLM_Gateway → Deepgram, etc.) exists,
so a future implementer needs no other file. Retire the `mcp_tools/` compat shim and
the top-level `Podcast MCP tools/` folder once all imports point at `_pipeline_core/`.

---

## Config & provenance rules (project conventions — keep these)

- **Provenance/storage stays auto-wired, never exposed as its own MCP tool.** The
  podcast pipeline's SQLite provenance writes (`_safe_provenance_write`, `get_store`)
  move into `_pipeline_core/` and are called internally by the tools — do not surface
  them as new registered tools.
- **Model choices stay configurable, not hardcoded.** Any Gemini/LLM/summarise model
  id must read from a config file (add/reuse a `tools/<group>/<tool>/config.py` or a
  shared config), not be a string literal in `logic.py`.

---

## Phases (server must stay runnable after each; run Phase 9 smoke test every time)

### Phase 0 — Prep & safety net
1. If not already under git, `git init` + commit the current tree so every phase is revertible.
2. Add `.gitignore` for `__pycache__/`, `*.pyc`, `.DS_Store`, `usage.json`, `.venv/`.
   Delete stray `.DS_Store` and `__pycache__/` dirs.
3. Record the **baseline tool inventory**: run the server, capture `list_tools()`
   output (total count + per-group names). This is the invariant the restructure
   must preserve (except the intentional `meeting_recorder` documents→media note,
   which is already registered under media).

### Phase 1 — Create `shared/` and move `backend/shared/`
1. `git mv backend/shared/ shared/` (root level).
2. Update the 4 import sites `from backend.shared.backend_utils import get_gemini_file`
   → `from shared.backend_utils import get_gemini_file`
   (credit_note_eval, credit_one_pager, ara, meeting_recorder — they move in Phase 3+).
3. In `mcp_server.py`, ensure `_ROOT` stays on `sys.path` so `import shared` resolves.
4. Smoke test.

### Phase 2 — Scaffold the new `tools/` root
1. Create `tools/__init__.py` with the pkgutil group auto-discovery (mirror the current
   `groups/__init__.py` logic, one level up).
2. Create each `tools/<group>/__init__.py` with pkgutil **tool** auto-discovery.
3. In `mcp_server.py`, switch `import groups` → `import tools`. Keep `groups/` in place
   for now (parallel) so nothing breaks mid-migration; delete it in Phase 8.
4. Smoke test (tools total may be 0 from the new root until Phase 3 — keep `groups/`
   imported too until the last group is migrated, OR migrate group-by-group and remove
   each old `groups/<g>` as its `tools/<g>` lands. Group-by-group is safer.)

### Phase 3 — Migrate the simple, independent tools (finance, documents, news, utility/file_upload)
For each tool in the mapping table with a clean 1-wiring→1-logic pair:
1. Create `tools/<group>/<tool>/`.
2. Move `backend/<group>/<file>.py` → `tools/<group>/<tool>/logic.py`; strip dead
   `FastMCP` imports; extract large prompt blocks → `prompts.py`; extract pydantic
   models → `contracts.py` (only where they exist).
3. Put registration in `tools/<group>/<tool>/__init__.py`:
   `from .tool import <fns>` then `register(group="<group>")(fn)`.
   Create `tool.py` holding the MCP-facing functions (import from `.logic`).
   For thin pass-through tools, `tool.py` may just re-export `logic` functions.
4. Write `README.md` for the tool (see Phase 8 doc rules).
5. Remove the corresponding old `groups/<group>/<file>.py` and empty `backend/<group>/`.
6. Smoke test — confirm those tools still appear in `list_tools()`.

### Phase 4 — Migrate the coupled feature folders (kg, vector_db, raw_data, research, utility/files+misc)
Same as Phase 3, but each lands as **one feature folder** holding multiple registered
tools (keep the modules together; do not split). For `research`, bring `research_tools/`
in as `tools/research/search/{sources/,clients.py,contracts.py,tool.py}` and simplify
the `research_tools` bootstrap in `mcp_server.py` (it can become a normal
`from tools.research...` import once it lives under the package).

### Phase 5 — Migrate the media cluster core (`_pipeline_core`)
1. Move all of `Podcast MCP tools/` into `tools/media/_pipeline_core/`, preserving its
   internal structure (storage/, contracts, ingestion/, automation/, claims/, backup.py).
2. Repoint every `from mcp_tools.*` import (currently only
   `groups/media/podcast_ingestion.py`) to `from tools.media._pipeline_core.*`.
3. Delete the `mcp_tools/` shim package and the top-level `Podcast MCP tools/` folder.
4. Smoke test.

### Phase 6 — Migrate the media tools
1. `youtube`, `image_gen`, `podcast` (with `prompts.py` from `podcast_prompts.py`),
   `meeting_recorder` (out of documents/, registered media) → own folders.
2. `podcast_ingestion` → `tools/media/podcast_pipeline/` feature folder. Its fat wiring
   (provenance logging, orchestration) moves into `tool.py`; the backend
   `podcast_ingestion.py` + `podcast_deliver.py` → `logic.py` (or a small `logic/`
   subpackage if two files read cleaner). Provenance helpers use `_pipeline_core`.
3. The scaffold tools (`transcribe`, `summarise`, `research`) → stub tool folders with
   detailed intent comments; keep them importable.
4. Smoke test.

### Phase 7 — Migrate remaining groups (knowledge)
1. `knowledge/memory` → own folder. Keep the sibling `agent/` `sys.path` insert in
   `mcp_server.py` untouched (see EXTERNAL TODOs).
2. Smoke test.

### Phase 8 — Cleanup + documentation (owner asked to "document everything")
1. Delete now-empty `groups/`, `backend/`, `research_tools/`, `mcp_tools/`,
   `Podcast MCP tools/` trees.
2. Simplify `mcp_server.py`: drop the `research_tools` `spec_from_file_location`
   bootstrap and the `backend/` path insert if no longer needed; keep `_ROOT` and the
   `agent/` insert.
3. **Per-tool `README.md`** (every tool/feature folder): one paragraph on what it does,
   the registered tool name(s) + signature, inputs/outputs, any env vars/config, and
   whether it's live or a stub.
4. **Rewrite `docs/ARCHITECTURE.md`** to describe the new single `tools/` root: the
   3-level pkgutil auto-discovery, the `register(group=...)` pattern, the
   `logic.py`/`tool.py` invariant, `shared/` and per-group `_shared/`, the media
   `_pipeline_core`, and the `agent/` external dependency.
5. **Keep the migration mapping table** (this file) as the historical record; add a
   one-line header noting the restructure is complete once done.
6. Update `docs/TOOLS_INVENTORY.md` / `AGENT_TOOLS_SUMMARY.md` to the new paths.

### Phase 9 — Smoke test (run after EVERY phase)
```bash
cd "mcp_server"
../.venv/bin/python -c "import mcp_server"          # no import errors
../.venv/bin/python mcp_server.py --dev             # Inspector boots clean; Ctrl+C
```
Confirm against the Phase 0 baseline:
- Same **total tool count** and same **per-group tool names** (via `list_tools()`).
- `assert_no_name_collisions()` passes.
- No `ModuleNotFoundError` for `backend.*`, `groups.*`, `mcp_tools.*`, `research_tools.*`.

---

## Definition of done
- One `tools/` root; no `backend/`, `groups/`, `research_tools/`, `mcp_tools/`, or
  `Podcast MCP tools/` folders remain.
- Every tool is a self-contained folder you can inspect in isolation.
- `logic.py` files import nothing from the registry/MCP.
- `list_tools()` output matches the Phase 0 baseline.
- Every tool folder has a README; `docs/ARCHITECTURE.md` reflects reality.
