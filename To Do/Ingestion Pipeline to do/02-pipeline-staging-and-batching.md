# Pipeline Staging and Batching

Part of Stage B of the ingestion roadmap
(`ingestion-pipeline/INGESTION_ARCHITECTURE_REFACTOR.md`). Do not start this
until Stage B's trigger condition in that document is met, and only after
`01-reader-writer-boundary-refactor.md` in this folder has settled — this
work builds on top of that boundary, not alongside it.

## The idea ("the factory floor")

The pipeline should have explicit holding areas between processing steps.
Information goes into a defined place and waits there until a batch is
ready, rather than one function doing discovery, extraction, review, and
delivery in memory in a single pass. Each processing step should be a
separate, independently testable function that reads from one holding area
and writes to the next — a factory floor, not a single machine that does
everything.

This is not a foreign idea being imported into this codebase — it is
already present in two places, narrowly:

- The coordinator's own SQLite ledger (`coordinator/state.py`) already holds
  items durably between stages (e.g. the `intake_publications` table) rather
  than keeping run state only in memory. This is what makes crash recovery
  and resumption work today.
- `sources/page_scanner/` already runs a staged sequence — detect → quality
  gate → OCR → group into passages → clean → store — with its own
  page/passage store tracking status per page (`page_scanner/store.py`).

This work generalizes that pattern deliberately, rather than inventing it.

## What changes

### Batch as the reviewed unit

Today the state machine is item-scoped by design:

```text
INTAKE_ITEM → INTAKE_ITEM         (self-loop: one item, then the next)
PROPOSAL_REVIEW → PROPOSAL_REVIEW (self-loop: one proposal, then the next)
```

with a single `INTAKE_BARRIER` between intake and capture. Making a batch —
not a single item — the reviewed unit requires new stages and new legal
transitions in `stages.py`. This is a state-machine change, not a policy
swap, which is why it sits here rather than alongside the judge gate or
grouped triplet review (both of which ship in Stage A without touching the
state machine).

Concretely, this means:

- A new holding stage where candidates accumulate until a batch is ready
  (by count, by time, or by an explicit "close the batch" action — decide
  which when this is picked up).
- New legal transitions in `LEGAL_TRANSITIONS` that move a batch as a unit
  through validation, review, and dispatch, rather than one item at a time.
- The existing per-item mechanics (`_pending_proposal`, gates, dispatch)
  operate *within* a batch once staging changes land — they don't get
  discarded, they get invoked once per item inside a batch stage instead of
  once per run.

### Explicit staging functions

Break the areas the original architecture document identified as pipeline
responsibilities into named, separate functions with an explicit holding
area between each, rather than steps inside one large routine:

1. Ask configured readers for candidates → **candidate holding area**.
2. Admit one candidate into the run.
3. Normalize into the shared model → **normalized holding area**.
4. Verify integrity and provenance.
5. Detect duplicates and superseding versions.
6. Apply confirmation and review policies (judge gate, grouped review) →
   **reviewed holding area**.
7. Produce stable highlights and knowledge proposals.
8. Create an approved, destination-independent envelope → **approved
   holding area** (this is close to what `ApprovedEnvelope` already is).
9. Route the envelope to configured writers.
10. Record each delivery attempt and receipt in the ledger.
11. Retry only unfinished or failed destinations.
12. Produce a truthful final run report.

The ledger extends to track which holding area each unit of work is
currently in, the same way it already tracks stage and status per run today.

## Why this is Stage B, not Stage A

This changes what "one unit of review" means at the state-machine level.
Stage A's grouped triplet review (see the main roadmap document) collapses
multiple triplet decisions *within* one envelope into one decision — that's
a UI/gate change, not a state-machine change, and ships now. Batching
*envelopes* or *items* together is a different, larger change to
`LEGAL_TRANSITIONS` and the ledger schema, and depends on the reader/writer
boundary from document 01 being settled first so there's a stable seam to
insert batch stages into.

## What must not change

- The ledger and state machine are carried forward, not reimplemented (see
  the main roadmap document's "one hard invariant"). Staging and batching
  extend the existing SQLite-backed approach; they do not replace it with a
  different mechanism.
- Crash recovery still resumes at the correct boundary — now the correct
  *batch* boundary, not just the correct item boundary. This needs an
  explicit test before this work is considered done, not an assumption that
  it still works.
- Successful destinations are still skipped during retries, per-item, even
  when items are grouped into a batch for review.

## Open questions to resolve when this is picked up

- What closes a batch — a count threshold, a time window, an explicit
  action, or some combination?
- Does a partially-reviewed batch (some items approved, some still pending)
  block the whole batch from dispatching, or do approved items dispatch
  independently as they clear?
- How does this interact with the LLM judge gate from Stage A — do
  judge-approved items get grouped separately from items still needing
  human review, so a human reviewer isn't waiting on judge output to see the
  batch?
