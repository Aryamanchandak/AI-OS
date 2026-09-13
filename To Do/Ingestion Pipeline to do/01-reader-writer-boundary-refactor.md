# Reader / Writer Boundary Refactor

Part of Stage B of the ingestion roadmap
(`ingestion-pipeline/INGESTION_ARCHITECTURE_REFACTOR.md`). Do not start this
until Stage B's trigger condition in that document is met.

## What this is

Source-specific reading and destination-specific writing should not live in
the central ingestion pipeline. The pipeline coordinates; readers and writers
own their own domain.

```text
Specialised readers
        |
        v
Ingestion pipeline
(normalize -> validate -> confirm -> route)
        |
        v
Specialised writers
```

```text
Reader:    "Here is what I found."
Pipeline:  "Is it valid and confirmed, and where should it go? How to store
            it — triplet-making, chunking, etc. — stays this function's job.
            The writer only writes to the destination, nothing else."
Writer:    "I know how to store it in that destination."
```

This is not new structure being invented — it's an existing seam being made
explicit. The codebase already reflects half of it: `sources/obsidian.py`,
`sources/markdown_tree.py`, `consumers/kg_consumer.py`,
`consumers/vector_consumer.py`, `publish/vault_writer.py`, `dispatch.py`.

## Design principles

1. The pipeline coordinates; integrations perform integration-specific work.
2. Every reader returns the same source-independent model.
3. Every writer accepts the same approved envelope and returns a receipt.
4. Source modules never write to destination systems.
5. Destination modules never discover or interpret source systems.
6. The pipeline owns validation, confirmation, routing, delivery state, and
   retries.
7. Writers own destination schemas, queries, transactions, and idempotent
   storage operations.
8. Existing public APIs remain stable while implementation moves behind them.
9. The sequential state machine remains visible in one place.

## Target structure

```text
src/ingestion/
├── coordinator/            # already exists; extend, do not duplicate
│   ├── coordinator.py
│   ├── gates.py
│   ├── stages.py
│   ├── state.py
│   ├── errors.py
│   ├── report.py
│   └── preflight.py
│
├── sources/
│   ├── base.py
│   ├── obsidian/
│   │   └── reader.py
│   ├── folders/
│   │   └── reader.py
│   ├── page_scanner/
│   │   └── reader.py
│   └── documents/
│       └── finder.py
│
├── destinations/
│   ├── base.py
│   ├── knowledge_graph/
│   │   └── writer.py
│   ├── vector_store/
│   │   └── writer.py
│   ├── content_database/
│   │   └── writer.py
│   └── obsidian/
│       └── writer.py
│
├── extraction/
└── intake/
```

Two corrections against an earlier sketch that mixed in ideas from an
external tool:

- **No parallel `core/coordinator.py`.** The real `coordinator/` package
  already exists with the file list above. It is the base to extend, not
  replace.
- **No `surfaces/` reader.** There is no surface, connector, or anything
  resembling one anywhere in the current codebase. Drop it from the target
  structure. Add a surface reader back only when there is an actual surface
  to read.

**Not yet placed:** `sources/markdown_tree.py` and `sources/book_metadata.py`
exist today and don't map cleanly onto `obsidian/`, `folders/`, or
`documents/`. `book_metadata` is load-bearing for `BookMetadataGate`, and
`gates.py` already imports it alongside `page_scanner.store` for that gate —
it likely belongs under `page_scanner/`, not `folders/`, since it's driving
book-*photo* identity rather than generic folder discovery. `markdown_tree`
may be shared discovery logic used by more than one reader and needs its own
look. Decide both explicitly during migration step 3 below rather than
guessing.

## Reader responsibilities

A reader may:

- Discover source candidates.
- Open and read source content.
- Interpret source-specific metadata.
- Preserve source-specific provenance.
- Report unreadable or malformed candidates.
- Maintain a source cursor or checkpoint when required.

A reader must not:

- Decide whether knowledge proposals are approved.
- Write into the knowledge graph, vector store, or content database.
- Know the schemas of destination systems.
- Control the overall ingestion run.

### Obsidian reader

Owns vault traversal, note filtering and exclusions, markdown/frontmatter
reading, Obsidian identity and path metadata, selection of changed or
eligible notes, and Obsidian-specific capture rules. The coordinator asks the
reader for candidates; it does not walk the vault or interpret Obsidian files
itself.

### Folder reader

Owns folder traversal, supported-file detection, folder and file filtering,
discovery of book-photo folders, stable paths, hashes, timestamps, and source
identifiers, and reporting unsupported or malformed inputs. Format-specific
extraction continues to be delegated to the existing PDF, Word, Markdown,
image, and legacy Word extractors.

The current allowed surface is intentionally narrow — one configured
`drop_folder` and a `vault_path` (`config.py`) — and expands deliberately as
new sources are added, not implicitly.

### Page scanner reader

This surface was missing from the earlier draft of the architecture
document and is substantial — larger than generic folder discovery, which
is why it stays its own reader rather than folding into `folders/`.

It already exists at `sources/page_scanner/` as a staged sequence:

- `detect.py` — highlight/mark detection on a scanned page.
- `images.py` — image loading and content hashing.
- `ocr.py` — OCR via `ocrmac`, producing lines and words.
- `photo_pipeline.py` — groups OCR'd words into passages, matches them
  against detected highlights.
- `quality.py` — blur/glare scoring and a quality gate that can reject a
  photo before it proceeds.
- `cleanup.py` — LLM-based passage text cleanup, with a diff guard limiting
  how far the model may deviate from the raw OCR text.
- `store.py` — its own SQLite store for pages and passages, including page
  status tracking.

**Open boundary question, to resolve during migration, not before:** most of
this is unambiguously reading (detection, OCR, hashing). But
`quality_gate()` and `clean_passages()` make judgment calls about whether
content is good enough and what its cleaned text should be — that leans
toward pipeline/normalization territory as this document defines it
elsewhere ("a reader must not decide whether knowledge proposals are
approved"). Resolve this by asking, for each function: is it deciding
something about *this specific candidate's* fitness to proceed (stays with
the reader, since it's source-specific judgment about a photo), or is it
applying a policy that should be uniform across all sources (moves to the
pipeline)? Quality gating is likely the former — it is specific to what a
scanned photo can suffer from and unlikely to generalize. LLM-based cleanup
is worth a closer look: if the same normalization should eventually apply to
OCR'd text from other photo-like sources, it belongs in the pipeline instead.

It is also the clearest existing example of a staged, multi-step process
already living in this codebase — detect → quality gate → OCR → group →
clean → store, each a separate function with its own store row for status.
Cited as prior art for that pattern in `02-pipeline-staging-and-batching.md`.

### Future document finder

Introduced as another source adapter behind `SourceReader`, not as new
branches inside the coordinator. It:

- Searches configured locations or indexes.
- Returns candidates rather than ingesting them directly.
- Attaches evidence explaining where each candidate was found.
- Leaves validation, confirmation, deduplication, and routing to the
  pipeline.

Adding document finding should not require changes to knowledge-graph,
vector-store, or content-database writers.

## Shared reader contract

```python
@dataclass(frozen=True)
class SourceCandidate:
    source_type: str
    source_id: str
    provenance: Mapping[str, object]
    # Enough to display or confirm a candidate before its full content is
    # read. Exact fields are finalized in migration step 2, against the
    # concrete needs of the Obsidian and folder readers first.


@dataclass(frozen=True)
class SourceDocument:
    source_type: str
    source_id: str
    content: str
    metadata: Mapping[str, object]
    provenance: Mapping[str, object]
    content_hash: str


class SourceReader(Protocol):
    def discover(self) -> Iterable[SourceCandidate]: ...
    def read(self, candidate: SourceCandidate) -> SourceDocument: ...
```

Discovery and reading are separate so a candidate can be displayed or
confirmed before its full content is processed when appropriate.

## Pipeline responsibilities

The central ingestion pipeline should own only behaviour shared across all
sources and destinations:

1. Ask configured readers for candidates.
2. Admit one candidate into the run.
3. Normalize it into the shared model.
4. Verify integrity and provenance.
5. Detect duplicates and superseding versions.
6. Apply confirmation and review policies.
7. Produce stable highlights and knowledge proposals.
8. Create an approved, destination-independent envelope.
9. Route that envelope to the configured writers.
10. Record each delivery attempt and receipt.
11. Retry only unfinished or failed destinations.
12. Produce a truthful final run report.

Readers only supply information for the pipeline to process — they do not
process it themselves. The pipeline reads the content, works out the
triplets, checks they make sense, and approves the batch (see
`02-pipeline-staging-and-batching.md` for how this is organized into
explicit stages).

The pipeline should not contain:

- Obsidian vault traversal.
- General filesystem traversal.
- Graph database queries.
- Vector database calls.
- Content database persistence details.
- Destination-specific schema construction.

## Writer responsibilities

A writer may:

- Translate an approved envelope into destination records.
- Apply destination identity and schema rules.
- Open database transactions.
- Perform idempotent writes.
- Verify the result of a write.
- Return a structured delivery receipt or failure.

A writer must not:

- Scan source systems.
- Ask the user for ingestion approval.
- Decide which other destinations should receive an envelope.
- Own cross-destination retry state.
- Mark the overall ingestion run complete.

### Knowledge-graph writer

Owns graph database connection details, node and relationship mapping,
identity resolution within the graph, graph queries and transactions, and
idempotent upsert behaviour. Storage stays in its existing database — the new
folder is the code boundary containing the writer that knows how to talk to
it.

### Vector-store writer

Owns chunk-to-vector-record mapping, embedding persistence rules,
vector-store identifiers and metadata, and idempotent upserts and
verification.

### Content-database writer

Owns content record mapping, database schema and transaction details,
idempotent content writes, and content-specific verification.

### Obsidian writer

Reading from Obsidian and writing to Obsidian are different responsibilities.
If ingestion publishes notes or highlights into the vault, that operation
belongs in an Obsidian writer, not in the Obsidian reader.

## Shared writer contract

```python
@dataclass(frozen=True)
class DeliveryReceipt:
    destination: str
    envelope_id: str
    status: str
    destination_id: str | None = None
    error: str | None = None


class DestinationWriter(Protocol):
    @property
    def destination(self) -> str: ...
    def write(self, envelope: ApprovedEnvelope) -> DeliveryReceipt: ...
```

The writer makes repeated delivery of the same envelope safe. The pipeline
keeps its own delivery ledger so it knows which destinations completed
successfully and which still need retrying.

## Migration approach

### 1. Protect existing behaviour

- Run and record the existing test baseline.
- Identify the public methods used by the cockpit, runner, and tests.
- Do not rename or remove public APIs during the first pass.
- Add characterization tests for any important flow that is not covered.

### 2. Define shared contracts

- Define `SourceCandidate` and `SourceDocument`.
- Define `SourceReader`.
- Confirm or define the stable approved-envelope type.
- Define `DestinationWriter` and `DeliveryReceipt`.
- Keep these models free of Obsidian, filesystem, graph, and vector details.

### 3. Extract readers

- Move Obsidian traversal and reading behind `ObsidianReader`.
- Move intake-folder discovery behind `FolderReader`.
- Decide the home for `markdown_tree.py` and `book_metadata.py`.
- Add the document finder later as another implementation of `SourceReader`.
- Keep format-specific extractors beneath the folder reader.

### 4. Extract writers

- Convert the knowledge-graph consumer into `KnowledgeGraphWriter`.
- Convert the vector consumer into `VectorStoreWriter`.
- Convert the content consumer into `ContentDatabaseWriter`.
- Move vault publication behind `ObsidianWriter` where applicable.
- Ensure each writer is independently idempotent and testable.

### 5. Thin the pipeline and coordinator

- Replace direct source traversal with reader calls.
- Replace destination-specific calls with writer calls.
- Keep confirmation, routing, dispatch state, and retries central.
- Keep the ordered `advance()` loop visible, but make each stage delegate
  its detailed work.

### 6. Verify and clean up

- Run focused tests after each extraction.
- Run the complete suite before deleting compatibility wrappers.
- Confirm crash recovery still resumes at the correct boundary.
- Confirm duplicate detection and version history remain unchanged.
- Confirm review decisions resume from the same point.
- Confirm successful destinations are skipped during retries.
- Update architectural documentation after the structure stabilizes.

## Completion criteria

- A new source can be added without editing destination writers.
- A new destination can be added without editing source readers.
- The coordinator does not traverse Obsidian or intake folders directly.
- The pipeline does not contain destination database operations.
- Each reader can be tested using only source fixtures.
- Each writer can be tested using an approved envelope fixture.
- Dispatch can retry one destination without repeating successful writes.
- The coordinator reads primarily as an ordered state machine.
- The main pipeline reads primarily as normalization, validation, review,
  routing, and delivery coordination.

## Non-goals

- Change the user-facing ingestion workflow beyond what Stage A already
  changed (judge gate, grouped review).
- Make the coordinator concurrent.
- Remove confirmation or review gates.
- Change duplicate or version semantics.
- Replace the existing databases.
- Redesign the knowledge model.
- Combine reading and writing merely because they involve the same external
  system.
