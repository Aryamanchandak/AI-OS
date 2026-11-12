# Database — data only

This folder is the **data store** for the personal ingestion pipeline. It
contains no code. All pipeline code lives in `../ingestion-pipeline/`
(see its README; the one-command runner is
`../ingestion-pipeline/scripts/ingest_obsidian.sh`).

| Folder | What it is |
|---|---|
| `Raw Data/bronze/` | Immutable captured markdown (chmod 0444) — the source of truth |
| `Raw Data/chats/`, `Raw Data/Agent Memory/` | Other captured/reference data |
| `Raw Data/backups/` | Ledger dump script + dumps |
| `Raw Data/_archive/` | Old pre-pipeline clutter (loose chat exports, the retired 380-file processing queue, `files/`) — safe to browse, nothing reads it |
| `sqlite/` | `ledger.db` (pipeline state: items/processing/runs/note_lineage/glossary) + `podcast_pipeline.db` (separate, producer elsewhere) |
| `chroma/` | ChromaDB vector store — derived, rebuildable from bronze |
| `Ingested/` | `study_system.db` — written by the study-system app (do not move) |
| `_trash/` | Staged deletions from the 2026-07-18 separation (old code dirs, the inbox vault mirror, stale docs). Review and empty when comfortable. |

Full record of the 2026-07-18 reorganisation:
`../ingestion-pipeline/docs/CHANGES_2026-07-18.md`
