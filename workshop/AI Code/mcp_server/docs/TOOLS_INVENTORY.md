# MCP Tool Inventory

Last updated: 2026-07-06 (post utility markdown workflow update)

Totals:

- **64** registry tools across **10** groups
- **1** server helper tool: `list_tools` (synthetic `other` group)
- **65** exposed tools in total

## Where the authoritative per-tool docs live

Each tool now has its own folder under `tools/<group>/<tool>/`, and each folder
carries a generated **`README.md`** listing its registered functions, signatures,
and purpose. Those folder READMEs — not this file — are the source of truth for a
tool's interface. See `ARCHITECTURE.md` for how the tree is wired.

## Groups and tool folders

| Group | Tool folder(s) | # tools |
|---|---|---|
| `documents` | `annual_report` | 1 |
| `finance` | `credit_note_eval`, `credit_one_pager`, `lease_deed` | 6 |
| `knowledge` | `memory` | 2 |
| `knowledge_graph` | `graph` | 5 |
| `media` | `youtube`, `image_gen`, `podcast`, `meeting_recorder`, `podcast_pipeline` | 23 |
| `news` | `market_brief` | 5 |
| `raw_data` | `capture` | 2 |
| `research` | `search` | 5 |
| `utility` | `web_search`, `fetch`, `suggest_file_path`, `create_folder`, `create_file`, `read_file`, `append_file`, `update_file`, `edit_file`, `list_dir`, `misc`, `file_upload` | 13 |
| `vector_db` | `search` | 2 |

## Operational notes

- **Research** tools are registered, but `tools/research/search/sources/` is a
  compatibility stub — calls return structured `source_unavailable` responses until
  a real backend is restored.
- **`fetch_url`** depends on `crawl4ai` (declared in `pyproject.toml`, may not be
  installed in every environment).
- **Podcast scaffold:** `tools/media/_pipeline_core/tools/` (`transcribe_episode`,
  `summarise_episode`, `research_episode_claims`) are dormant, **not** registered —
  they await an LLM_Gateway → Deepgram endpoint.
- **External deps:** knowledge tools need the sibling `agent/` project; kg/vector
  tools need `Database/knowledge-graph/src` and `Database/vector-db/src`; `raw_data`
  needs `RAW_DATA_ROOT`. See `ARCHITECTURE.md` → External dependencies.

## Regenerating this / the folder READMEs

The per-folder READMEs are generated from the live registry (each registered
function's `__module__` maps to its `tools/<group>/<tool>/` folder, docstrings become
the descriptions). Regenerate after adding or changing tools.
