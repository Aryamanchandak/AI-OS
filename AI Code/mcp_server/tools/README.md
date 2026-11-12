# `tools/` — the single tool root

Every MCP tool lives here, **one folder per tool**, grouped by domain:
`tools/<group>/<tool>/`. Open a tool's folder and you have all of it — its
registration, logic, prompts, and contracts — nothing scattered across other trees.

## Anatomy of a tool folder

```
tools/<group>/<tool>/
├── __init__.py    # registers the tool: register(group="<group>")(fn)
├── logic.py       # pure implementation (backend-backed tools)  — OR —
├── tool.py        # MCP-facing fns with @register (inline tools)
├── prompts.py     # prompt templates        (only if the tool has any)
├── contracts.py   # pydantic/dataclass models (only if the tool has any)
└── README.md      # generated: registered functions + signatures + purpose
```

**Pure-logic rule:** `logic.py` imports nothing from the registry or MCP, so it stays
testable without booting the server. Flow is one-way: `__init__ → tool/logic → prompts/contracts`.

## Auto-discovery

`tools/__init__.py` imports each `<group>`; each `<group>/__init__.py` imports each
`<tool>`; each `<tool>/__init__.py` registers. Subpackages starting with `_`
(e.g. `media/_pipeline_core/`) are shared support code and are **not** auto-imported
as tools.

## Groups

| Group | Tools |
|---|---|
| `documents` | annual_report |
| `finance` | credit_note_eval, credit_one_pager, lease_deed |
| `knowledge` | memory |
| `knowledge_graph` | graph |
| `media` | youtube, image_gen, podcast, meeting_recorder, podcast_pipeline (+ `_pipeline_core`) |
| `news` | market_brief |
| `raw_data` | capture |
| `research` | search |
| `utility` | web_search, fetch, suggest_file_path, create_folder, create_file, read_file, append_file, update_file, edit_file, list_dir, misc, file_upload |
| `vector_db` | search |

## Adding a new tool

1. Create `tools/<group>/<tool>/`.
2. Put the implementation in `logic.py` (pure) — or `tool.py` if it's small/inline.
3. In `__init__.py`: `from .logic import fn` then `register(group="<group>")(fn)`.

That's it — auto-discovery picks it up on next server start. No central list to edit.

See `../docs/ARCHITECTURE.md` for the full picture.
