# 01: Break Up the Ingestion Code (Reader / Writer Boundary and Beyond) [ I THINK 

**This is the first plan.** Start here. (Updated 2026-10-13. It used to be
"Stage B, don't start yet". See decision M1 in `00-DECISIONS.md`.)

Read `00-CURRENT-FLOW-AND-BREAKUP.md` first. It shows the flow today and
the target layout on one page. This plan is the step-by-step version.

## What this is

**We are breaking the code up, not rewriting it (M2).** Every piece of
ingestion code is moved into a folder that does one job. **What the code
does stays exactly the same.** Every move is proven with targeted checks.

The original idea of this plan still holds at its heart:

```text
Readers   →   Pipeline   →   Writers
```

- **Reader:** "Here's what I found." It finds and opens one kind of
  source: the Obsidian vault, the drop folder, or book photos.
- **Pipeline:** "Is it valid and approved, and where should it go?" It
  does the checking, splitting, extraction, flag rules and review.
- **Writer:** "I know how to store it there." It talks to one destination:
  the graph, the vector store, the content database, or the vault.

What's new in this version is that **everything else gets the same
treatment**:

- the intake checks
- capture
- splitting
- extraction
- the flag rules
- the ingestion database
- the coordinator
- the API
- AI access

The full list and target folders are in `00-CURRENT-FLOW-AND-BREAKUP.md`
§4.

**Why first:** the code has grown into one tangle, with several jobs
packed into each big file. You want to build the judge, batching and the
rest **once, properly, on clean ground**.

**The cost of going first:** we fix the structure before the judge and
batching exist. So the layout leaves **empty slots** for them (`review/`
for the judge, `llm/` for the Batch API), but builds nothing.

## The rules

1. **Move, don't change.** No behaviour changes inside a move.
2. **One piece per step.** Each step can be checked and undone on its own.
3. **No fixes inside a move.** Bugs found during a move go into that
   component's review doc and get their own separate fix step.
4. **The ledger is moved, never rewritten.** That's `coordinator/stages.py`
   and `coordinator/state.py`. Their contents must be identical before and
   after.
5. **The edges stay the same:**
   - the UI's API (`openapi.json`)
   - the database files and tables
   - `runner.py`'s public functions
6. **Old import paths keep working** until the final cleanup step, so
   nothing breaks halfway.
7. **The pipeline coordinates.** It never walks a vault or queries a
   database itself.
8. **Readers never write to stores. Writers never look at sources.**
9. **The step-by-step run order stays visible in one place.**

## Targeted checks (how every move is proven)

For every step:

1. **Before:** a small test that pins what this piece does *today*, run on
   its own. If none exists, write it first, as its own step.
2. **Move** the piece.
3. **After:**
   - the same test passes unchanged
   - the full suite passes unchanged (460 collected on 2026-10-13)
   - `openapi.json` is unchanged
   - the database tables are unchanged
   - `stages.py` and `state.py` have only moved, not changed
4. **Write it down** in the component's review doc: what moved, what was
   checked, and any bugs found.

## Before anything moves

1. **Component reviews.** One doc per piece, CR-01 to CR-11, in
   `component-reviews/`. Written in fresh chats with prompt P2 in
   `FRESH-CHAT-PROMPTS.md`.
   - Each one says how the piece works, what the code expects of it, its
     test gaps, and the targeted checks to add.
   - **The move for a piece doesn't start until its review is read and
     agreed.**
2. **Record the baseline:** the full test run results, `openapi.json`, and
   the database table definitions.
3. **Add pinning tests for the untested pieces:** the flag rules
   (`review_policy.py`) and the ingestion database (`store.py`).

## The order of moves

The rule of thumb: best-tested and least connected first, the coordinator
last.

| Step | Move | Component review |
| --- | --- | --- |
| 1 | Writers → `destinations/` (graph, vector, content, vault, dispatch) | CR-09 |
| 2 | Readers → `sources/` (Obsidian, folders, page scanner, book identity) | CR-01, CR-02, CR-03 |
| 3 | Intake checks → `intake_gates/` (one file per gate; `text_cleanup/` unchanged inside) | CR-04 |
| 4 | Flag rules and review queue → `review/` | CR-05, CR-08 |
| 5 | Capture, splitting and extraction out of `pipeline.py` | CR-06, CR-07 |
| 6 | Split `store.py` → `storage/` (same tables) | CR-08 |
| 7 | One AI access path → `llm/` | CR-11 |
| 8 | Split `server.py` → `api/` | CR-10 |
| 9 | Split `coordinator.py` (the ledger is moved only) | CR-10 |
| 10 | Move `preview.py` out of the real code; remove the temporary old import paths | CR-10 |

## Open questions carried over (settle them during the move, not before)

- **Page scanner:** are the photo-quality check and the AI cleanup
  "reading", or "pipeline" work? The test is *is it specific to photos?*
  Quality probably is. Cleanup might not be.
- **Book identity:** it probably belongs with the page scanner.
- **Markdown folder walker:** it probably goes with the drop-folder reader.

## Done when

- Every piece lives in its own folder, as in
  `00-CURRENT-FLOW-AND-BREAKUP.md` §4.
- The full test suite passes unchanged, plus every new pinning test.
- `openapi.json`, the database tables, `stages.py` and `state.py` are
  unchanged.
- A new source can be added without touching any writer. A new
  destination can be added without touching any reader.
- Searching the `coordinator/` folder for "neo4j", "chroma" or "vault"
  finds nothing.
- The AI is called through one path only.
- Every component review records what moved and what was checked.

## Not in scope

- Building the judge, batching, the Batch API or new models. They come
  after.
- Fixing bugs, which get logged and fixed as separate steps. For example,
  the missing filter file (F1) and cleanup not running on Obsidian notes
  (F2).
- Changing how review, duplicates or versions behave.
- Replacing any database or redesigning the knowledge model.

## Where in the code

All paths are under `gateway/src/gateway/ingestion/`. The full module map,
with sizes, is in `00-CURRENT-FLOW-AND-BREAKUP.md` §2.

- **Biggest split targets:**
  - `coordinator/coordinator.py`: 1,372 lines, with `view()` at lines
    215–831
  - `pipeline.py`: 795 lines, with `parse_source()` at 336–647
  - `store.py`: 910 lines
  - `server.py`: 772 lines, about 45 data shapes
- **The 4 AI chat clients to merge:**
  - `extraction/gateway.py:45`
  - `parsing.py:110`
  - `runner.py:42`
  - `text_cleanup/spelling.py`
- **Ledger, moved only:** `coordinator/stages.py`, `coordinator/state.py`.
- **Public callers to keep stable:**
  - `server.py` routes
  - `runner.py`
  - `gateway/ingestion_tests/`
  - `gateway/openapi.json`
  - `shell/src/api/schema.d.ts`
- **Shared shapes, as a sketch:**
  - `SourceReader` with `discover()` and `read()`
  - `DestinationWriter` with `write(envelope)`, which returns a
    `DeliveryReceipt`
  - These are only introduced where they formalise what already exists.
    No new behaviour.

## Appendix: detail kept from the earlier version of this plan

These sections come from the version of this plan before 2026-10-13. They
still describe the target for readers, the pipeline and writers. Where
they say "A1 clerk", read "judge".

### The readers

- **Obsidian reader:** walks the vault, skips excluded notes, reads
  markdown and frontmatter, and picks out new or changed notes.
- **Folder reader:** walks the drop folder, spots supported file types,
  and records paths, hashes and timestamps. Reading PDFs, Word files and
  the like stays with the existing format-specific readers underneath it.
- **Photo (page scanner) reader:** the biggest one. It already runs a
  staged sequence: find highlights on the page → check photo quality →
  OCR → group into passages → LLM cleanup → save. **Open question:** the
  quality check and the LLM cleanup are judgement calls, not just reading.
  Settle this during the move with one test: *is this specific to
  photos?* If yes, it stays with the reader. If it should apply to every
  source, it moves to the pipeline. The quality check is probably
  photo-specific. Cleanup might not be.
- **Future document finder:** added later as just another reader. It
  finds candidates and says where they came from, and leaves everything
  else to the pipeline.

Two existing files don't have an obvious home yet: the markdown folder
walker and the book-metadata lookup. The book lookup probably belongs with
the photo reader, since it's about identifying the book in the photos.
Decide both during the move, not before.
### What the pipeline does

1. Ask readers for new candidates.
2. Take one in.
3. Put it into the shared shape.
4. Check it's intact and record where it came from.
5. Spot duplicates and newer versions.
6. Apply the approval and review rules (the gates, and the A1 clerk and its review screen).
7. Make the highlights and facts.
8. Produce an approved item that doesn't depend on any one destination.
9. Send it to each writer.
10. Record each delivery and its receipt.
11. Retry only the destinations that failed.
12. Write an honest run report.
### The writers

- **Knowledge-graph writer:** turns facts into nodes and links, handles
  identity, and makes repeated writes safe.
- **Vector-store writer:** turns chunks into vector records and metadata,
  and makes repeated writes safe.
- **Content-database writer:** keeps the record of what was ingested.
- **Obsidian writer:** writing notes back into the vault is a separate
  job from reading the vault, so it gets its own writer.
### Where in the code (earlier version: readers, writers, layout, shapes, settings)

All paths are under `gateway/src/gateway/ingestion/`.

- **Today's readers:** `sources/obsidian.py`, `sources/markdown_tree.py`,
  `sources/book_metadata.py`, and `sources/page_scanner/`. The page
  scanner contains:
  - `detect.py`
  - `images.py`
  - `ocr.py`
  - `photo_pipeline.py`
  - `quality.py` (`quality_gate()`)
  - `cleanup.py` (`clean_passages()`)
  - `store.py`
- **Today's writers:** `consumers/kg_consumer.py`,
  `consumers/vector_consumer.py`, `publish/vault_writer.py`, and
  `dispatch.py` (the dispatcher).
- **Format readers:** `intake/extractors/`.
- **Coordinator (extend it, don't replace it):** `coordinator/`. It holds
  `coordinator.py`, `gates.py`, `stages.py`, `state.py`, `errors.py`,
  `report.py` and `preflight.py`.
- **Target layout:**
  - `sources/{base.py, obsidian/, folders/, page_scanner/, documents/}`
  - `destinations/{base.py, knowledge_graph/, vector_store/, content_database/, obsidian/}`

  There is no new `core/coordinator.py`, and no `surfaces/` folder. Those
  came from an unrelated tool's sketch.
- **Shared shapes, as a sketch:**
  - `SourceCandidate` (source type, id, provenance) and `SourceDocument`
    (adds content, metadata and content hash).
  - `SourceReader` with `discover()` and `read(candidate)`.
  - `DestinationWriter` with `destination` and `write(envelope)`, which
    returns a `DeliveryReceipt` (destination, envelope id, status,
    destination id, error).
- **Settings:** `config.py` holds `drop_folder` and `vault_path`.
- **Public callers to keep stable:** `server.py`, `runner.py`, and the
  tests in `gateway/ingestion_tests/`.

## Aryaman's comments

