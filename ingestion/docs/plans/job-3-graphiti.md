# Job 3: Graphiti replaces the hand-built graph layer

Date: 2026-11-12. Status: outline only, nothing implemented. Detailed when job 2 is done.

## What

Graphiti (the library that reads a passage, pulls out entities and facts, merges duplicates and dates each fact) takes over the graph. You have closed that decision: Graphiti first, a hybrid with your own evidence checks is a later version 2, your own layer is out.

## What gets deleted

About 2,900 lines of source: `kg/*` (1,874), `extraction/*` (621), `consumers/kg_consumer.py` (215) and most of `review_policy.py` (206). Also the proposal-review parts of `pipeline.py`, `models.py` and `store.py` (the `review_queue` and `review_items` tables), because Graphiti writes straight to the graph and there are no proposals left to review. Their tests go with them: `test_kg_store.py`, `test_kg_consumer.py`, `test_kg_preflight.py` and `test_extraction_gateway.py`, about 1,250 lines. Test deletions are listed for your approval in the step that makes them.

## What gets written

One adapter file, `graph_adapter.py`, under 200 lines and the only file that imports Graphiti. It holds three small plug-ins (chat, embeddings, a do-nothing reranker) that call `gateway_client.py`. One consumer, `consumers/graphiti_consumer.py`, that hands each highlight's text to Graphiti as one episode and records the episode ID against the highlight ID in the ledger, so every fact traces back to its source.

## Steps, one commit each

Step 1 installs `graphiti-core` at a pinned version and records it in `DEPENDENCIES.md`. Then I read the installed source and confirm the notes in `gateway/docs/integrations/graphiti.md`, which were written from a download and never checked against an install.

Step 2 writes the adapter, tests first. The tests are the ones you already marked: no call ever reaches a provider directly, gateway down is a clear error with no fallback, vectors are 768 long, the token never appears in logs, extraction sends temperature 0.

Step 3 is one real passage in and one fact out, linked to that passage, on a wiped Neo4j.

Step 4 writes the consumer and runs it next to the old `kg_consumer.py` on the same real notes, so you can compare the two graphs.

Step 5 switches over and deletes the old code, listed for approval first.

## Done when

One real note goes through capture, Graphiti and search, and the returned fact points at the right highlight. Wiping the graph and running job 2's rebuild restores it. During the whole run only the gateway (127.0.0.1:8000) and Neo4j (127.0.0.1:7687) are contacted. Every Graphiti model call appears in the gateway's call log.

## Needs your answer before starting

Which models answer Graphiti's "medium" calls (extraction) and "small" calls (duplicate checks)? Today's extraction profile is Claude Sonnet.

Should entity summaries be on or off? Your earlier plan turned them off; you asked why, and that is still unanswered. They cost extra model calls per entity and are what makes Graphiti's entity pages readable.

How big is one episode: a highlight, a section or a whole note? I'd start with one highlight, since the highlight is already your stable unit.

Retries: Graphiti retries each call up to 4 times and the gateway now retries zero times, so they do not stack. Confirm that stays.

## Depends on

Job 2 (rebuild, and capture not needing Neo4j). The gateway passing its live checks with real keys. A new dependency, so it needs your OK at step 1.

## Not in this job

Attaching CIN/ISIN/NSE/BSE IDs to entities, claims and scenarios, custom entity types, communities, and the hybrid version 2.
