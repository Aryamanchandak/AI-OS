# Iteration 2 — Live Capture Admission (T45, Part 3 of 3)

| Field | Value |
|---|---|
| **Status** | **Parked — do not build now** |
| **Owner** | Repository coordinator |
| **Receives later** | One approved durable capture from Part 2 |
| **Must preserve** | Sequential stages, review gates, retry, restart recovery |
| **Must not own** | Rectangle UI, OCR editing UI, draft storage design |

## Outcome

Admit an approved durable live capture into the existing pipeline without the
frontend calling `pipeline.capture()` directly and without creating a second
state machine.

This is a future coordinator design problem. No coordinator change is required
for the current build.

## Why a new seam is needed later

The current coordinator discovers files in intake and captures Obsidian. It
does not accept an approved on-screen capture produced while the app is open.

Calling the low-level pipeline directly from the frontend would bypass the
coordinator's stage order, mandatory decisions, retry rules, reports, locking,
and restart behavior. An in-memory `CaptureRequest` would also disappear if the
process closed at the wrong moment.

## Admission designs to compare

### Option A — materialized intake artifact

Part 2 writes an approved, validated artifact into a durable intake location.
The coordinator discovers it through an extractor/producer adapter and follows
the ordinary intake sequence.

Questions:

- Can existing discovery express one parent with several selections and image
  crops without awkward file conventions?
- At which stage does text capture occur?
- How is an approved artifact distinguished from an editable draft?

### Option B — durable live-capture queue

Part 2 marks an artifact approved. A typed coordinator operation admits its
stable identifier from a durable queue/store. The coordinator reads the
artifact, records admission idempotently, and processes it at a legal stage.

Questions:

- Which store owns pending/admitted status?
- How does `start_run()` re-derive approved but unadmitted work?
- Does admission happen before normal intake discovery or as a named source
  within it?

The later design pass must choose one. It must not create both paths.

## Required sequencing contract

```text
durable approved artifact
  -> coordinator discovers/adopts it exactly once
  -> capture text selections as one parent plus N user selections
  -> parse each exact selection without model re-segmentation
  -> extract
  -> mandatory semantic review where policy requires it
  -> dispatch
  -> report completion/failure
```

Visual selections remain attached durable artifacts and follow only the
downstream behavior approved under T59. The coordinator must not pretend they
are ordinary OCR text highlights.

## Restart and idempotency requirements

- Approval and admission are separately durable states.
- Retrying admission cannot duplicate the parent, selections, or crops.
- A crash after capture but before recording admission is detectable and
  recoverable.
- A crash after recording admission but before parse resumes from durable
  owner stores using the coordinator's established recovery model.
- Starting a new process finds approved/unadmitted work without relying on
  frontend memory.
- Failed admission is visible and retryable; it does not discard the approved
  artifact.
- The coordinator remains the only owner of stage advancement.

## Reuse

- `src/ingestion/coordinator/` supplies stage order and legal operations.
- `src/ingestion/models.py` supplies `CaptureRequest` and `UserSelection` for
  exact text selections.
- `src/ingestion/parsing.py` supplies the landed `user_selection` behavior.
- `BOOK_HIGHLIGHT_FLOW.md` and
  `src/ingestion/sources/obsidian.py::capture_book_highlights()` demonstrate
  the shared-parent/multiple-selection result that live capture should match.

Do not add a frontend-owned queue, call one direct pipeline operation per
rectangle, or create a parallel live-capture coordinator.

## First design work when un-parked

1. Audit the then-current coordinator and Part 2 artifact contract.
2. Compare Option A and Option B against restart seams and existing storage.
3. Choose one admission owner and one idempotency key.
4. Define typed inputs, returned `RunView`/error behavior, and reporting.
5. Specify crash-boundary and duplicate-admission tests.
6. Obtain approval before changing coordinator code.
