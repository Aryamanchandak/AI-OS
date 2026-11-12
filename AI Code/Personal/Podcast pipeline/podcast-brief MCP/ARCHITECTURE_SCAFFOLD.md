# Architecture Scaffold

This directory structure is the reduced target shape for this project.

The current runtime code has been intentionally cut back. The folders that remain are ownership boundaries first, implementation areas second.

## Ownership Direction

- `ingestion/` stays podcast-specific and remains in this project.
- `adapters/` is the repo-side seam for external services such as the LLM gateway.
- `mcp_tools/` owns MCP-oriented tools, contracts, summarisation, transcription, and automation helpers.
- `delivery/` is its own domain.
- `research/` is a root-level boundary for external research integration.
- `databases/sqlite/` owns operational SQLite schema and access patterns.
- `databases/vector_db/` owns vector persistence adapters.
- `databases/knowledge_graph/` owns knowledge-graph persistence adapters.
- `interface/` remains as inactive local placeholders and is not the active integration surface.

## Current Intent

This scaffold is deliberately light on implementation. It is here to:

1. Reduce accidental expansion of the current codebase.
2. Make future migration targets explicit.
3. Keep orchestration, LLM, storage, delivery, and MCP concerns separated before code is rebuilt.
