# MCP Server Architecture

> Restructured to a **single `tools/` root, one folder per tool** (2026-07-05).
> The old split `backend/` (logic) + `groups/` (wiring) mirrored trees are gone —
> each tool now lives entirely in its own folder. See
> `docs/MIGRATION_LOG.md` for the exact old→new mapping.

## Entry Point

`mcp_server.py` is the server entry point. It:

- Adds `mcp_server/` and the sibling `agent/` project to `sys.path`.
- Imports `tools`, which auto-discovers every group and every tool inside it,
  running each tool's `register(group=...)` call as a side effect of import.
- Runs `tool_registry.assert_no_name_collisions()`.
- Attaches every registered function to `FastMCP`.
- Adds `list_tools()` for agent introspection.

## The one folder per tool

```
tools/
├── __init__.py                 # auto-discovers each <group> (skips names starting with _)
└── <group>/
    ├── __init__.py             # auto-discovers each tool subpackage in the group
    └── <tool>/
        ├── __init__.py         # register(group="<group>")(fn) for each tool fn
        ├── logic.py            # pure implementation (no MCP/registry imports)
        ├── tool.py             # (inline tools) MCP-facing fns w/ @register — used
        │                       #   instead of logic.py where the tool was always inline
        ├── prompts.py          # prompt templates (only if the tool has any)
        └── contracts.py        # pydantic/dataclass models (only if the tool has any)
```

Open one folder → see the whole tool. Nothing about a tool lives in another tree.

### Two shapes of tool folder

- **Backend-backed** (`logic.py` + `__init__.py`): the implementation was previously
  in `backend/<group>/<tool>.py`. `__init__.py` imports the functions from `.logic`
  and registers them. Example: `tools/finance/lease_deed/`.
- **Inline** (`tool.py` + `__init__.py`): the tool was always defined inline with
  `@register(...)` decorators (mostly `utility/`). The file moved to `tool.py`; the
  `__init__.py` is just `from . import tool` to trigger the decorators.

## Auto-discovery (3 levels)

`pkgutil.iter_modules` walks each level:

1. `tools/__init__.py` imports every `<group>` package.
2. `tools/<group>/__init__.py` imports every `<tool>` package.
3. `tools/<group>/<tool>/__init__.py` calls `tool_registry.register`.

**Convention:** subpackages whose name starts with `_` (e.g. `_pipeline_core`) are
support code, **not** auto-imported as tools. They're imported explicitly by the
tools that need them.

## Registration pattern

```python
# tools/<group>/<tool>/__init__.py
from tool_registry import register
from .logic import some_function

register(group="finance")(some_function)
```

`tool_registry` is unchanged: a simple in-memory list of `ToolEntry(fn, group)`,
read once at startup by `mcp_server.py`.

## The pure-logic invariant

`logic.py` imports **nothing** from `tool_registry`, `mcp`/FastMCP, or its own
package's `__init__.py`/`tool.py`. Dependencies flow one direction:
`__init__.py → tool.py/logic.py → prompts.py/contracts.py`. This keeps tool logic
importable and testable without booting the MCP server, e.g.:

```python
from tools.finance.lease_deed.logic import build_rent_roll   # no server needed
```

## Groups (10) and their tools (64)

- **documents** — `annual_report`
- **finance** — `credit_note_eval`, `credit_one_pager`, `lease_deed`
- **knowledge** — `memory` (index/search; depends on sibling `agent/`)
- **knowledge_graph** — `graph` (5 kg_* tools)
- **media** — `youtube`, `image_gen`, `podcast`, `meeting_recorder`, `podcast_pipeline`
  (+ `_pipeline_core`, the shared podcast provenance/storage/claims subsystem)
- **news** — `market_brief`
- **raw_data** — `capture`
- **research** — `search` (5 source wrappers + bundled `sources/` clients)
- **utility** — `web_search`, `fetch`, `suggest_file_path`, `create_folder`,
  `create_file`, `read_file`, `append_file`, `update_file`, `edit_file`,
  `list_dir`, `misc`, `file_upload`
- **vector_db** — `search`

`list_tools()` adds itself under a synthetic `other` group at runtime, so FastMCP
reports 65 tools total (64 registered + `list_tools`).

## Coupled feature folders

Where several registered tools cross-import or share state, they live together in
one folder rather than being split artificially (the owner will split these into
strict one-tool-per-folder later):

- `media/podcast_pipeline/` — 11 tools sharing the SQLite provenance store; its
  `tool.py` also imports `tools/media/youtube/logic.py` (`summarize_youtube_video`)
  and the shared `_pipeline_core`.
- `media/_pipeline_core/` — the former standalone "Podcast MCP tools" subsystem
  (ingestion bridge, SQLite storage, contracts, claims extraction/verification,
  automation workflows, backup). Imported on demand, not auto-registered.
  Its `tools/` subfolder (`transcribe_episode`, `summarise_episode`,
  `research_episode_claims`) is **scaffold** — dormant, not registered, waiting on an
  LLM_Gateway → Deepgram endpoint.
- `research/search/`, `knowledge_graph/graph/`, `vector_db/search/`,
  `raw_data/capture/`, `utility/misc/` — multi-tool folders.

## Shared code

- `shared/backend_utils.py` (root) — Gemini API-key/client helpers, Files API
  reference normalization/lookup, upload polling, and the deliberately narrow
  PDF-only inline bytes helper. Imported by finance/documents/media tools.
- `sandbox.py`, `usage.py` (root) — sandbox path guards and usage tracking, imported
  by several utility/knowledge tools.

## External dependencies (outside `mcp_server/`)

These live in **sibling** projects and are on `sys.path` at runtime, not vendored here:

- **`agent/`** — `mcp_server.py` adds `<workspace>/agent` to `sys.path` so
  `tools/knowledge/memory/tool.py` can import `memory`, `vector_index`, `schemas`,
  `gateway`, `artifacts`. ⚠️ The hardcoded path is `os.path.dirname(_ROOT)/agent`;
  in this workspace the folder is actually at `AI Agent/agent/`, so a launcher must
  put that on `PYTHONPATH` (the smoke-test harness does this explicitly).
- **`knowledge_graph`** (`Database/knowledge-graph/src`) and **`vector_db`**
  (`Database/vector-db/src`) — imported by the kg / vector tools.
- **`RAW_DATA_ROOT`** env var — `raw_data/capture` imports `lib.capture` from that path.

## Smoke test

```bash
cd mcp_server
export PYTHONPATH="<ws>/AI Agent/agent:<ws>/Database/knowledge-graph/src:<ws>/Database/vector-db/src"
.venv/bin/python -c "import mcp_server; from tool_registry import get_all; print(len(get_all()))"
# expect: 62
```

## Dependencies

Runtime dependencies are listed in `mcp_server/pyproject.toml`. The `research/search`
tools ship a local compatibility implementation under
`tools/research/search/sources/` that returns structured `source_unavailable` errors
until a real research backend is restored.
