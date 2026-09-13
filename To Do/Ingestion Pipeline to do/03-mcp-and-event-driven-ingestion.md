# MCP Surface and Event-Driven Ingestion

The MCP surface is a Stage A item (see the main roadmap document,
`ingestion-pipeline/INGESTION_ARCHITECTURE_REFACTOR.md`) — it can start now.
Event-driven ingestion is Stage B and depends on
`02-pipeline-staging-and-batching.md` in this folder. Both are documented
together here because they're the same underlying ambition at different
maturity levels: give agents (and eventually events) the same access to
ingestion that the coordinator has today.

## MCP surface (Stage A — start now)

Expose the pipeline's existing reading and writing capabilities to agents as
MCP tools, without duplicating logic.

- **Tools are thin wrappers, not new implementations.** They call directly
  into functions that already exist: `consumers/kg_consumer.py`,
  `consumers/vector_consumer.py`, `consumers/content_consumer.py`,
  `dispatch.py`, and the reader modules once they exist behind
  `SourceReader` (document 01). This is deliberate: whatever Stage B
  relocates these functions to, the MCP wrappers move with them unchanged,
  because they never held their own copy of the logic.
- **Granularity: one `write` and one `query` tool per destination.** A
  separate tool per operation ("check if KG is live," "extract X," "extract
  Y," "write") was considered and rejected — there's no current need driving
  that granularity, and it multiplies the surface area to maintain for no
  present benefit. Revisit only if a real use case needs finer control.
- Readers are exposed as callable discovery/read tools the same way, once
  they exist as `SourceReader` implementations rather than logic embedded in
  the coordinator.

This item does not require the folder restructuring in document 01 to be
finished first — it can wrap the current `consumers/*` and `sources/*` code
as-is. It becomes cheaper and cleaner once document 01 lands, but isn't
blocked on it.

## Event-driven ingestion (Stage B — sequenced last)

The longer-term aim: some sources (a new Obsidian note, a new dropped file)
trigger ingestion automatically on the event, instead of waiting for a
manual or scheduled run.

**The real tension, stated plainly:** "process immediately when something
happens" and "pause for confirmation before anything is finalized" pull in
opposite directions. An event-driven trigger that bypassed the review gates
this system exists to preserve would be a much bigger behavioural change
than anything else in this roadmap — and isn't what's being proposed.

**The resolution:** an event trigger feeds a candidate into the same durable
staging path everything else uses (document 02). It does not bypass the
ledger, the review gates, or the judge gate — it only changes *when a
candidate gets discovered and admitted*, not what happens to it afterward.
A new file appearing triggers "add this to the candidate holding area," not
"ingest and publish this immediately."

**Why this waits for Stage B's staging model specifically:** without
explicit holding areas and batch boundaries (document 02), an event firing
mid-batch, or many events firing close together, has no defined place to
land. The staging model is what gives an event trigger somewhere safe to
put its output. Building event triggers before that model exists means
building them against a moving target.

## Sequencing summary

1. MCP surface over current reader/writer functions — Stage A, start now.
2. Reader/writer boundary refactor — Stage B, document 01.
3. Pipeline staging and batching — Stage B, document 02, depends on (2).
4. Event-driven triggering — Stage B, depends on (3). MCP tools from step 1
   remain the same interface agents and event handlers both call through.
