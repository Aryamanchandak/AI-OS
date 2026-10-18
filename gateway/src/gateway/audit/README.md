# Durable audit events

This folder owns the append-only SQLite audit repository. `store.py` implements `AuditStore`; `__init__.py` exports it for other gateway packages.

Construction creates `audit_log`, indexes for time/session/channel queries, and a version-1 schema marker. `append()` writes a timestamped event containing channel identity, trust level, event type, optional session/tool/policy metadata, and serialized parameters/results. Each append is autocommitted, and database failures propagate to the caller.

`query()` returns newest events with optional session and channel filters. JSON payload columns are returned as stored strings. `healthcheck()` verifies the schema version.

The LLM pipeline writes `llm.call` events during finalization, and explicit embedding requests write `llm.embed` events. Those callers supply metadata rather than full prompts and completions. The repository itself accepts arbitrary payloads and performs serialization, not general-purpose content redaction.

The database path comes from `GLCPaths.audit_db`. See [database helper](../platform/database/README.md) and [orchestration](../llm/orchestration/README.md).
