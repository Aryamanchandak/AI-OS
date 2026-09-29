# Reader / Writer Boundary Refactor [ I THINK 

Stage B, first item. **Don't start** until the Stage B checklist in
`INGESTION_ARCHITECTURE_REFACTOR.md` is met.

## What this is

Split the ingestion code into three clear jobs:

```text
Readers   →   Pipeline   →   Writers
```

- **Reader:** "Here's what I found." It knows how to find and open one
  kind of source: the Obsidian vault, the drop folder, or book photos.
- **Pipeline:** "Is it valid and approved, and where should it go?" It
  also turns content into what gets stored, making the triplets and the
  vector chunks. The writer only writes to its destination, nothing else.
- **Writer:** "I know how to store it there." It knows how to talk to one
  destination: the knowledge graph, the vector store, the content
  database, or the Obsidian vault.

**In plain terms:** the pipeline never knows how a vault is laid out or
how the graph database is queried. It asks readers "what's new?" and tells
writers "store this."

**Why:** adding a new source should never mean touching graph code, and
adding a new destination should never mean touching Obsidian code. Today
the pieces mostly exist but aren't cleanly separated, so a change in one
place can reach into another.

**This isn't inventing new structure.** Half of it already exists: there
are separate files for reading Obsidian, reading folders, writing to the
graph, writing to the vector store and writing to the vault. This makes
the boundary explicit and enforced.

## The rules

1. The pipeline coordinates. It never walks a vault or queries a database
   itself.
2. Every reader hands back the same shape of result, whatever the source.
3. Every writer accepts the same shape of approved item and hands back a
   receipt.
4. Readers never write to stores.
5. Writers never look at sources.
6. The pipeline owns checking, approval, routing, delivery tracking and
   retries.
7. Writers own their database's layout and queries, and make repeated
   writes safe.
8. Nothing that other code calls from outside changes during the move.
9. The step-by-step run order stays visible in one place.

## The readers

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

## What the pipeline does

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

## The writers

- **Knowledge-graph writer:** turns facts into nodes and links, handles
  identity, and makes repeated writes safe.
- **Vector-store writer:** turns chunks into vector records and metadata,
  and makes repeated writes safe.
- **Content-database writer:** keeps the record of what was ingested.
- **Obsidian writer:** writing notes back into the vault is a separate
  job from reading the vault, so it gets its own writer.

## How to do the move, step by step

1. **Protect what works:** record the current test results and add tests
   for any important flow that isn't covered. Don't rename anything
   public.
2. **Define the shared shapes:** what a reader returns, what a writer
   accepts, and what a receipt looks like. Keep them free of any Obsidian,
   folder, graph or vector details.
3. **Move the readers** behind the shared shape, one at a time.
4. **Move the writers** behind the shared shape, one at a time. Each one
   must be safe to repeat and testable on its own.
5. **Thin the pipeline:** replace direct source and database code with
   reader and writer calls. Keep the run order visible.
6. **Check nothing broke:** after a crash, the run resumes at the right
   place. Duplicates and versions behave the same. Review decisions
   resume. Destinations that already succeeded are skipped on retry.

## Done when

- A new source can be added without touching any writer.
- A new destination can be added without touching any reader.
- The pipeline and coordinator contain no vault walking, folder walking or
  database code. The quick check: searching the coordinator folder for
  "neo4j", "chroma" or "vault" finds nothing.
- Each reader can be tested with only sample source files.
- Each writer can be tested with only a sample approved item.
- One failed destination can be retried without repeating the others.

## Not in scope

- Changing how review feels beyond what Stage A already changed.
- Running things in parallel inside the coordinator. Parallel fact and
  vector workers are considered in 02, Decision 4.
- Removing the approval or review gates.
- Changing how duplicates or versions work.
- Replacing any database, or redesigning the knowledge model.

## Where in the code

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

