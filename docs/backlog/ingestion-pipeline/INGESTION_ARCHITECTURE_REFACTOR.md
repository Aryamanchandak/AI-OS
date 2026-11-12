# Ingestion Roadmap

## What this is

This is the source of truth for where ingestion is going and in what
order. Each item has its own plan document in this folder.

- For decisions, read `00-DECISIONS.md`.
- For the flow today and the breakup, read `00-CURRENT-FLOW-AND-BREAKUP.md`.
- For the plain-English overview, read `00-macro-view.md`.

> **Reordered 2026-10-13 (decision M1).** The breakup of the code now
> comes **first**. This reverses the earlier approach, which was "build
> features on the current code first, restructure later". It was your
> call: the code has become too tangled to keep building on, and you want
> each piece built properly once.
>
> **The cost:** the structure is fixed before the judge and batching
> exist. So the breakup leaves empty slots for them, but builds nothing.
> The old "Stage B unlock checklist" no longer applies and has been
> removed.

## The order

| # | Phase | Plan | In one line | Status |
| --- | --- | --- | --- | --- |
| 0 | **Component reviews** | `component-reviews/CR-01 … CR-11` | One review per piece: how it works, what's expected of it, its test gaps and targeted checks | **Next.** Prompts are ready. |
| 1 | **Break up the code** | `01-reader-writer-boundary-refactor.md` | Move every piece into its own folder. Behaviour unchanged, proven by targeted checks. | **First plan** |
| 2 | **Gateway: new models + Batch API** | `To Do/Gateway to do/02-models-and-batch-api.md` (to be written) | Opus / Sonnet / Haiku 5.5 and others, plus the Batch API, done together | Can run alongside 0–1 (it's in the gateway, not ingestion) |
| 3 | LLM judge | `A1-llm-judge-gate.md`, `A1-llm-judge-gate-SIMPLE.md` (+ A1b policy, A1c rejection causes) | A Batch API worker that says yes or no to facts, controlled from the UI | After 1 and 2 |
| 4 | Every intake check, one by one | `A4-intake-gates-review.md` | Cut unnecessary clicks before fact review; make the drop folder a setting | After 1 |
| 5 | Agents submit content | `03-mcp-surface.md` | Agents hand notes to ingestion through MCP, with the same review | After 1 |
| 6 | Holding areas and batches | `02-pipeline-staging-and-batching.md` | Work moves in batches between holding areas; facts and vectors run in parallel | After 3 |
| 7 | Automatic start | `05-event-driven-ingestion.md` | Ingestion starts by itself when something changes | Last |
| — | Gateway serves every screen | `A3-ui-ownership-closeout.md` | Checklist only | Mostly done |

**Side plans asked for on 2026-10-13** (see `00-DECISIONS.md` §5):

- page-scanner batching (A5)
- prompts folder (A6)
- opinions and who holds them (A7)
- people and entity resolution (A8)

Their place in the order is set once they're written.

## The one hard rule

The **ledger** is the saved record of each step. It lets a crashed run
resume exactly where it stopped, and retry without repeating work. It is
**moved, never rewritten**, including during the breakup.

## Key points (still true)

- The judge approves **through the same approve function you use**. That's
  the pipeline's `resolve_proposal_reviews()`, which also stores the
  result. Not the store's lower-level version, which only marks a fact
  approved.
- The judge never auto-rejects. It has no kill switch and no watch-only
  trial (M12). If it fails, facts stay in your queue.
- Agents (03) never write to a database directly. Their content goes
  through the same review as everything else.

## Tracked elsewhere

**Agents reading the databases** is a separate plan:
`To Do/AI Agent to do/02-agent-database-read-access.md`. It shares the MCP
server from plan 03.

## Not doing

- Rewriting code as part of the breakup. It's a move, not a rewrite (M2).
- Rewriting the ledger, ever.
- Changing how duplicates and versions work.
- Replacing any database, or redesigning the knowledge model.
- Letting any source, including agents, store anything without review.

## Where in the code

All paths are under `gateway/src/gateway/ingestion/`. The old
`ingestion-pipeline/merged-ingestion/` copy is only a backup.

- Ledger and run rules: `coordinator/state.py`, and `coordinator/stages.py`
  (`LEGAL_TRANSITIONS`).
- The approve function the judge must use: `pipeline.py`
  `UnifiedIngestionPipeline.resolve_proposal_reviews()`. Don't use
  `store.resolve_proposal_reviews()`, because it doesn't dispatch.
- Intake gates: `coordinator/gates.py`. Fact review is the coordinator's
  separate `gate == "proposal"` path.
- Full module map: `00-CURRENT-FLOW-AND-BREAKUP.md` §2.

## Aryaman's comments

