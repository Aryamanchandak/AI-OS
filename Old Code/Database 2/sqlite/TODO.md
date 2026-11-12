# SQLite TODO

## Ledger DB (new)

`ledger.db` is the cross-system ingestion tracking database, managed by `Raw Data/lib/ledger.py`.
Tables: `items`, `processing`, `runs`.
Schema: `Raw Data/lib/ledger.sql`.
Backup script: `Raw Data/backups/dump_ledger.sh`

This is NOT the podcast pipeline store — that remains `podcast_pipeline.db`.

## Podcast pipeline ingester and routing

`podcast_pipeline.db` is now the operational provenance store for the podcast MCP tool
scaffolds. The next database-side step is not schema work inside this folder; it is a
structured podcast pipeline ingester plus an information router, similar in role to the
existing vector DB and knowledge graph ingestion flows elsewhere in the project.

Expected follow-up:
- Add an ingester that reads podcast pipeline artifacts and writes normalized provenance
  into `podcast_pipeline.db`.
- Add a router layer that decides which podcast-derived records should remain in SQLite
  versus being forwarded into the vector DB and knowledge graph systems.
- Keep this as tracking only for now. The MCP tool scaffolds already point at
  `Database/sqlite/podcast_pipeline.db`, but the cross-system ingestion path does not
  exist yet.

## Future: sqlite consumer (Phase 2)

When the sqlite consumer is built (per IMPLEMENTATION_PLAN Phase 2.2), it will:
- Read `pending('sqlite', 'written')` from `ledger.db`
- Write normalized rows into a new `content_store.db` (or `podcast_pipeline.db` if scope is limited to podcast)
- Mark `(content_hash, 'sqlite', 'written', 'done')` in `ledger.db`
