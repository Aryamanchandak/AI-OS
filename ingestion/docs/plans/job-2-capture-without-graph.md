# Job 2: capture must not depend on the graph

Date: 2026-11-12. Status: plan only, nothing implemented. Waiting for your OK on the rule change below.

## What

Make the raw (bronze) layer stand on its own, so the graph can be wiped and rebuilt from it at any time. This is the decoupling you asked for in the Graphiti plan comments, and it has to land before Graphiti (job 3) so the swap only touches graph code.

## What ties them together today

Three things. `ids.py`, which mints the stable highlight IDs, imports a helper from the `kg/` folder, so deleting `kg/` would break the bronze layer. `runner.py` opens Neo4j and checks it before anything else, and refuses to capture a single note if that check fails. And there is no way to say "rebuild the graph": the ledger remembers that an item was already sent to the graph and skips it forever.

The good news is the middle is already clean. `dispatch.py` hands each item to the graph, vector and SQLite stores independently and records each result separately, so one failing store does not block the others.

## The rule change (needs your OK)

Today: Neo4j down means refuse everything. Proposed: Neo4j down means capture, parse, vector and SQLite all carry on, and the graph work is left pending and picked up on the next run. Extraction is untouched in this job; it is replaced in job 3.

## Steps, one commit each

Step 1 is a pure move. `concept_id_for` is only used by the graph, so it moves from `ids.py` to `kg/identity.py`, and `ids.py` stops importing from `kg/`. Its tests in `test_ids.py` move with it. No ID changes value; the existing ID tests prove that.

Step 2 is the rule change. `runner.py` builds the capture stack first and adds the graph store only if Neo4j answers. `coordinator/preflight.py` reports Neo4j as a warning instead of a blocker. One existing test in `test_runner.py` asserts the old rule (failed check, nothing happens); it is replaced by tests for the new rule, and I will show you that test before changing it.

Step 3 adds rebuild. One new function in `pipeline.py`, about 20 lines, that forgets the "already sent" marks for one store and replays every approved item from the ledger through the existing `retry_dispatches`. No new dependency.

## What gets deleted or replaced

Nothing large is deleted in this job; it is the cut that makes job 3's deletions safe. Replaced: the "Neo4j first" block in `runner.py` (about 15 lines) and the Neo4j blocker in `coordinator/preflight.py`. Moved: `concept_id_for` (about 15 lines).

## Done when

With Neo4j stopped, running one real note captures it, parses it, writes vectors and SQLite rows, and reports the graph as pending. With Neo4j started, the next run fills the graph without calling the model again. After wiping the graph, rebuild restores the same number of nodes and links as before. All 460 existing tests still pass, apart from the one replaced in step 2.

## Not in this job

Graphiti itself, removing the old extractor, and shrinking the coordinator. Under Graphiti the rebuild will replay highlight text rather than stored extractions; the command stays the same, only what it replays changes.
