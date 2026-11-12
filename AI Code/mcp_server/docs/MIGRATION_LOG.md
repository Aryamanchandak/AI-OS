# Migration Log — Per-Tool Folder Restructure (2026-07-05)

Executed the plan in `PER_TOOL_RESTRUCTURE_PLAN.md`. Goal: collapse the mirrored
`backend/` (logic) + `groups/` (wiring) trees and the scattered "Podcast MCP tools"
subsystem into a **single `tools/` root, one folder per tool**.

**Original restructure result: 62 registered tools across 10 groups — byte-for-byte
identical inventory to the pre-restructure baseline** (verified after every step via
`list_tools()` diff).

Later on 2026-07-05, the separate `tools/utility/gemini/` upload tool was retired and
its local-file upload behavior was consolidated into `tools/utility/file_upload/`.
Current inventory is 61 registered tools across 10 groups.

## What moved where

| Old location(s) | New location |
|---|---|
| `backend/shared/` | `shared/` (root) |
| `backend/finance/credit_note_eval.py` + `groups/finance/credit_note_eval.py` | `tools/finance/credit_note_eval/{logic,__init__}.py` |
| `backend/finance/credit_one_pager.py` + wiring | `tools/finance/credit_one_pager/` |
| `backend/finance/lease_deed.py` + wiring | `tools/finance/lease_deed/` |
| `backend/documents/ara.py` + `groups/documents/annual_report.py` | `tools/documents/annual_report/` |
| `backend/news/market_brief.py` + wiring | `tools/news/market_brief/` |
| `backend/knowledge_graph/tools.py` + wiring | `tools/knowledge_graph/graph/` |
| `backend/vector_db/tools.py` + wiring | `tools/vector_db/search/` |
| `backend/raw_data/tools.py` + wiring | `tools/raw_data/capture/` |
| `research_tools/{sources,contracts.py}` + `groups/research/{search,clients}.py` | `tools/research/search/{sources/,contracts,clients,tool}.py` |
| `groups/utility/web_search.py` (inline) | `tools/utility/web_search/tool.py` |
| `groups/utility/fetch.py` (inline) | `tools/utility/fetch/tool.py` |
| `groups/utility/files.py` (inline, 5 tools) | `tools/utility/files/tool.py` |
| `groups/utility/utils.py` (inline, 2 tools) | `tools/utility/misc/tool.py` |
| `groups/utility/gemini.py` (inline) | retired after restructure; local Gemini upload behavior now lives in `tools/utility/file_upload/` |
| `backend/utility/file_upload.py` + wiring | `tools/utility/file_upload/` |
| `groups/knowledge/memory_tools.py` (inline) | `tools/knowledge/memory/tool.py` |
| `backend/media/youtube_intelligence.py` + wiring | `tools/media/youtube/` |
| `backend/media/image_gen.py` + wiring | `tools/media/image_gen/` |
| `backend/media/podcast.py` + wiring | `tools/media/podcast/logic.py` |
| `backend/media/podcast_prompts.py` (orphan) | `tools/media/podcast/prompts.py` |
| `backend/documents/meeting_recorder.py` + `groups/media/meeting_recorder.py` | `tools/media/meeting_recorder/` |
| `backend/media/podcast_ingestion.py` | `tools/media/podcast_pipeline/ingestion.py` |
| `backend/media/podcast_deliver.py` | `tools/media/podcast_pipeline/deliver.py` |
| `groups/media/podcast_ingestion.py` (fat wiring) | `tools/media/podcast_pipeline/tool.py` |
| `Podcast MCP tools/` (whole subsystem) | `tools/media/_pipeline_core/` |
| `mcp_tools/` (compat shim) | **deleted** (imports repointed to `_pipeline_core`) |

## Import rewrites

- `from backend.shared.backend_utils` → `from shared.backend_utils` (4 sites).
- `from backend.<group>.<mod>` → co-located `from .logic` / cross-tool
  `from tools.<group>.<tool>.logic`.
- Podcast subsystem: every `mcp_tools.X` → `tools.media._pipeline_core.X`
  (self-imports across the subsystem + the one external consumer, `podcast_pipeline/tool.py`).
- `research_tools.X` → relative `.sources.X` / `.contracts` inside
  `tools/research/search/`.

## `mcp_server.py` changes

- Removed the `research_tools` `spec_from_file_location` bootstrap (now a normal
  package under `tools/`) and the now-unused `import importlib.util`.
- Replaced `import groups` with `import tools`.
- Kept the sibling `agent/` `sys.path` insert **unchanged** (external dependency).

## Deliberate non-changes (to preserve the baseline)

- **Vestigial local `FastMCP` instances** in `credit_note_eval/logic.py`,
  `annual_report/logic.py`, `market_brief/logic.py` were left in place. They build an
  unused local `mcp = FastMCP(...)` and decorate functions with `@mcp.tool()`; removing
  them changes what object the registry captures. Flagged for a later polish pass.
- **Scaffold episode tools** (`_pipeline_core/tools/{transcribe,summarise,research}.py`)
  were **not** registered as MCP tools — they weren't in the baseline (they return
  stub responses pending an LLM_Gateway → Deepgram endpoint). Left dormant.
- **Prompt/contract extraction** was mostly deferred: prompts remain inline in
  `logic.py` except where a separate file already existed. This was a structural move,
  not a rewrite.

## Verification

Reusable harness captured a baseline inventory (62 tools / 10 groups) before any
change and diffed `list_tools()` output after **every** step — all identical. Final
runtime check invoked tools end-to-end (`get_time`, `lease_deed.logic`,
`podcast_pipeline` deep `_pipeline_core` chain) to confirm co-located imports resolve
at call time, not just at import.
