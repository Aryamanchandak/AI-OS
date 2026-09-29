# Ingestion Roadmap

## What this is

This is the source of truth for where ingestion is going and in what
order. Each item has its own plan document in this folder. This page only
says what the items are, in what order, and what unlocks the next stage.
For the plain-English overview, read `00-macro-view.md`.

## The approach, in two stages

- **Stage A (now):** make review faster and add new abilities **on the
  current code**, without restructuring it.
- **Stage B (later):** once Stage A has been used for real, restructure
  the code: split readers from writers, add holding areas and batches,
  then automatic triggers.

**Why this order:** we don't yet know the right structure for batching,
an LLM judge or agent tools. Building the features first, on code that
works, turns guesses into evidence. Then the restructuring happens once,
informed, rather than being guessed at twice.

## The one hard rule

The **ledger** (the saved record of each step, which lets a crashed run
resume exactly where it stopped, and retry without repeating work) is
**moved, never rewritten**. Rewriting it would throw away a lot of
hard-won edge-case handling at the same time as the review process is
changing. Those two changes must never happen together.

## Stage A: build now

| # | Item | Plan | In one line | Status |
|---|---|---|---|---|
| 1 | LLM judge | `A1-llm-judge-gate.md` | A clerk LLM approves most flagged facts. It watches first, then acts. | Start now |
| 2 | ~~Approve a sentence at once~~ | Folded into `A1-llm-judge-gate.md` | When you're needed, decide a whole highlight's facts in one submit. | Folded into A1 (2026-09-28) |
| 3 | Gateway serves every screen | `A3-ui-ownership-closeout.md` | Checklist only. | Mostly done |
| 4 | Agents submit content | `03-mcp-surface.md` | Agents hand ingestion notes through MCP, with the same review. | Start now |
| 5 | Every intake check, one by one | `A4-intake-gates-review.md` | Cut unnecessary clicks before fact review; drop folder becomes a setting. | Start now (added 2026-09-28) |

**Order:** A1 → A4 → 03 → A3 ticks off.

**Key points:**

- The clerk (A1) approves **through the same approve function you use**.
  That's the pipeline's approve function, which also stores the result,
  not the lower-level one that only marks it approved. Using the wrong
  one would mark facts approved that never reach the stores. (This
  corrects an earlier version of this page.)
- Agents (03) never write to a database directly. Their content goes
  through the same review as everything else.

**Stage A doesn't:**

- restructure folders
- rewrite the ledger
- introduce batch review
- add automatic triggers

## Stage B: restructure, once unlocked

Stage B starts only when **all** of these are true:

- The clerk (A1) is live and has been used on real runs.
- A3's checklist is complete.
- At least one real agent workflow uses the MCP tools (03).
- There's real evidence of how far the clerk can be trusted, and where
  you still need to be involved.

Then, in order:

1. **`01-reader-writer-boundary-refactor.md`:** separate reading sources
   from writing stores.
2. **`02-pipeline-staging-and-batching.md`:** holding areas between steps,
   work in batches, and the parallel fact and vector workers. This is
   committed.
3. **`05-event-driven-ingestion.md`:** ingestion starts by itself when
   something changes. Noticing a change only adds it to the waiting pile.

## Tracked elsewhere

**Agents reading the databases** (querying the graph, the vector store
and the content database) is a separate plan:
`To Do/AI Agent to do/02-agent-database-read-access.md`. It shares the MCP
server from plan 03.

## Not doing

- Restructuring before Stage B is unlocked.
- Rewriting the ledger, ever.
- Running the coordinator's steps concurrently in Stage A.
- Changing how duplicates and versions work.
- Replacing any database, or redesigning the knowledge model.
- Letting any source, including agents, store anything without review.

## Where in the code

All paths are under `gateway/src/gateway/ingestion/`. The old
`ingestion-pipeline/merged-ingestion/` copy is only a backup.

- Ledger and run rules: `coordinator/state.py`, and `coordinator/stages.py`
  (`LEGAL_TRANSITIONS`).
- Approve function the clerk must use: `pipeline.py`
  `UnifiedIngestionPipeline.resolve_proposal_reviews()`. Don't use
  `store.resolve_proposal_reviews()`: it doesn't dispatch.
- Intake gates: `coordinator/gates.py`. Fact review is the coordinator's
  separate `gate == "proposal"` path.

## Aryaman's comments

