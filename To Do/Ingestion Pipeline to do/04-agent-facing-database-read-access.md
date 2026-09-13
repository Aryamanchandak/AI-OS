# Agent-Facing Database Read Access

**Status: scoping only. This is not designed yet, deliberately.** It is a
separate initiative from the ingestion roadmap, not a section of it — writing
is ingestion's job; reading for agents is a different capability with
different requirements. This document exists so the intent isn't lost, not
to lock in an architecture before real use cases exist.

## The gap

Ingestion already has writers for every destination: `KnowledgeGraphWriter`
(`kg/kg_store.py`, `consumers/kg_consumer.py`), a vector-store writer
(`vector/vector_store.py`, `consumers/vector_consumer.py`), and a
content-database writer (`content_store.py`, `consumers/content_consumer.py`).
Data lands in `Database/neo4j`, `Database/chroma`, and `Database/sqlite`.

There is currently no equivalent **read** path for agents. What exists today
that looks adjacent, and isn't it:

- `gateway/main.py` mounts `cockpit.server.create_router` — this serves the
  human review cockpit (pending decisions, run state), not general query
  access to the knowledge graph, vector store, or content database.
- Nothing in the codebase currently lets an agent ask the knowledge graph a
  question, run a similarity search against the vector store, or look up a
  content record, outside of ingestion's own internal use of those stores
  while writing to them.

This is the gap this document names: agents that want to *use* what's been
ingested — not ingest more — have nowhere to go yet.

## Why this is separate from the ingestion roadmap

- Different consumer: ingestion's writers are called by the pipeline, for
  the pipeline's own data. This capability is called by arbitrary agents,
  for their own purposes, potentially concurrently with ingestion runs.
- Different access shape: writes are structured, schema-validated, and
  idempotent by design. Reads need to support open-ended questions (semantic
  search, graph traversal, lookups) that don't map onto "replay this
  operation safely."
- Different risk profile: a bad write is caught by validation and review
  gates before it lands. A bad or unbounded read (an agent running an
  expensive graph query, or a query that leaks data it shouldn't) needs its
  own guardrails that have nothing to do with ingestion's gates.

Building this as an extension of ingestion's writers would couple two
things that don't share a lifecycle or a threat model.

## What this shares with the MCP work in ingestion

Document `03-mcp-and-event-driven-ingestion.md` proposes exposing
ingestion's *writers* as MCP tools for agents. This capability is the read
counterpart, and could plausibly share the same MCP transport/server once
both exist — an agent calling one MCP endpoint to write and another to
query. But the tool implementations, access rules, and query shapes are
independent design work, not a byproduct of the write-side MCP surface.

## Open questions to resolve before design starts

These are intentionally unanswered — they're what a real design pass needs
to settle, not decisions made in advance of use cases:

- **Query interface shape.** Raw Cypher/SQL access, a constrained set of
  query templates, a semantic-search wrapper, or some combination — this
  differs a lot per store (graph traversal vs. vector similarity vs. content
  lookup) and picking one shape for all three may not make sense.
- **Read-only enforcement.** How is it guaranteed that a "read" tool can't
  be used to write or delete? At the query-permission level (DB user with
  read-only grants) or at the application level (allowlisted query shapes)?
- **Access boundaries.** Does every agent get the same read access, or does
  this need per-agent or per-workflow scoping? Is there data in these stores
  that shouldn't be broadly queryable?
- **Where this lives.** Its own small service, a module inside `gateway/`,
  or something else — not `merged-ingestion/`, per the separation argument
  above.
- **What's actually needed first.** This document doesn't yet know which
  concrete agent workflow is waiting on this. Naming that first would turn
  the questions above from abstract into answerable.

## Non-goals (for now)

- This does not change or extend any ingestion writer.
- This does not attempt to unify querying across all three stores into one
  interface unless the open questions above conclude that's right.
- This does not start implementation. The next step is naming a concrete
  use case, not picking a query language.
