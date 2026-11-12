# `_pipeline_core` — shared podcast-pipeline subsystem

**Not a tool.** The leading `_` marks this as shared support code: it is imported on
demand by `tools/media/podcast_pipeline/`, never auto-registered. It was formerly the
standalone top-level **"Podcast MCP tools"** tree, folded in here during the 2026-07-05
restructure (all `mcp_tools.*` imports were repointed to
`tools.media._pipeline_core.*` and the `mcp_tools/` compat shim was deleted).

## Contents

| Path | Role |
|---|---|
| `storage/` | SQLite provenance store (`get_store`, `SQLiteStateStore`) pointing at `Database/sqlite/podcast_pipeline.db` — episodes, artifacts, tool runs, claims. |
| `shared/contracts.py` | Pydantic row models (`EpisodeRow`, `ArtifactRow`, `RunRow`, `ClaimRow`, `ToolExecutionRow`, batches). |
| `contracts/episode.py` | `EpisodeToolRequest` / `EpisodeToolResponse` — the episode-tool boundary types. |
| `ingestion/bridge.py` | `sync_episode_artifacts` — reconciles on-disk pipeline artifacts into SQLite. |
| `backup.py` | `backup_db` — hot-copy backup of the provenance DB. |
| `claims/` | Claim extraction & verification services + contracts (generic boundaries only; research-specific wiring deferred). |
| `automation/workflows.py` | Declarative pipeline step definitions. |
| `tools/` | **Scaffold** episode tools — see below. |

## Scaffold (`tools/`) — dormant, not registered

`tools/{transcribe,summarise,research}.py` define `transcribe_episode`,
`summarise_episode`, and `research_episode_claims`. They return stub responses and are
**not** registered as MCP tools (they were never in the tool inventory). They are
blocked on an LLM_Gateway → Deepgram transcription endpoint; each file carries an
intent comment describing what to build. Wire them up and register them (add a
`podcast_pipeline`-style folder, or register from here) when that dependency lands.

## Provenance is auto-wired, not exposed

The storage/backup calls here are invoked internally by `podcast_pipeline`'s tool
functions (provenance logging on every download/summary/delivery). They are
intentionally **not** surfaced as their own MCP tools.
