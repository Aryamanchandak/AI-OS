# Ingestion 2 — functionality catalog

Reviewed 13 October 2026. Scope: the code currently present in `merged-ingestion`, including 69 Python files (16,351 lines), two shell scripts, package configuration, and Obsidian filter configuration. This is a source-code catalog, not a claim that the external services have been tested or are running. Python syntax was checked without importing or executing ingestion. No application code was changed.

## What this system is

This is a Python backend for turning documents, Obsidian notes, and photographs of highlighted book pages into traceable, searchable knowledge. It prepares readable text, retains captures, splits text into meaningful passages, asks an LLM for concepts/claims/relationships, routes questionable results to human review, and projects accepted results into SQLite, Neo4j, and Chroma.

It contains two connected workflows:

1. **File intake:** dropped files → text extraction → book identification when needed → abbreviation/spelling review → content approval when needed → Obsidian publication → original-file archiving.
2. **Knowledge ingestion:** Obsidian notes and approved book passages → captured text → highlights → semantic extraction → review when needed → content database, knowledge graph, and vector index.

The full coordinator connects both workflows. Lower-level runners and helpers also allow individual parts to be used separately.

## Vocabulary used by the code


| Term                | What it is                                                | Why it exists                                                                            |
| ------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Intake result       | Extracted Markdown, title, metadata, and an approval flag | Common output format for PDF, Word, Markdown, and image extractors                       |
| Source record       | One captured version of UTF-8 text                        | Records content hashes, origin, timestamps, and version lineage                          |
| Capture             | An observation/import event                               | Records repeated encounters even when the underlying content is already stored           |
| Canonical record    | Representative record for normalized-equivalent content   | Avoids processing structurally equivalent text repeatedly                                |
| Highlight           | An exact text passage, with position and optional context | The main unit of knowledge extraction and downstream identity                            |
| User selection      | Explicit passage boundaries supplied by a producer        | Preserves selected text without asking the segmentation model to select it again         |
| Concept             | A named idea or entity, such as “working memory”          | Vocabulary for graph nodes and claims                                                    |
| Claim               | An assertion about one or more concepts                   | Stores what the source says, alongside supporting evidence                               |
| Relation            | A subject–predicate–object proposal                       | Connects concepts, e.g. “A is a prerequisite of B”                                       |
| Evidence            | A verbatim quote and its character range                  | Lets code check that an extracted assertion actually points into its source highlight    |
| Envelope            | A validated package for one extracted highlight           | Carries provenance, proposals, access rules, and review state to all consumers           |
| Consumer/projection | An adapter that writes an envelope into another store     | Gives the same accepted highlight relational, graph, and semantic-search representations |
| Vector chunk        | A smaller piece of a highlight used for embeddings        | Keeps search inputs within size limits without redefining the stored highlight           |




## Main functionality catalog



### 1. File intake and format conversion

**What it is:** the shared front door for files placed in a drop folder.

**What it does:** picks exactly one extractor per supported file, computes the original file hash, extracts text, and returns an `IntakeResult`. Publishing and moving the original are separate operations; a source moves only after its note has been written.


| Format               | Core behavior                                                                                   | Important boundary                                                                                 |
| -------------------- | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Markdown (`.md`)     | Reads UTF-8 text and performs basic text sanity checks                                          | No format conversion or prose rewriting                                                            |
| PDF (`.pdf`)         | Uses embedded text per page; falls back to rendered-page OCR where needed                       | OCR pages require approval; this is text extraction, not full PDF layout reconstruction            |
| Word (`.docx`)       | Reads paragraphs and tables in document order; renders common headings/lists/tables as Markdown | Embedded images are counted and flagged for review, not extracted                                  |
| Legacy Word (`.doc`) | Converts with macOS `textutil`, then reuses DOCX extraction                                     | Heading styles and table structure may be lost; detected or uncertain table loss triggers approval |
| Images               | Reads highlighted passages from photographed pages                                              | Supports JPG/JPEG, PNG, HEIC/HEIF, TIFF/TIF, BMP; all photo OCR results require approval           |


The full coordinator accepts text documents at the drop-folder top level and photos in one-level book folders. It refuses top-level photos, unexpected files inside book folders, and deeper folders other than `_retake`. The standalone `run_funnel` helper only scans top-level files and does not implement the full coordinator's book-folder workflow.

### 2. Highlighted book-page scanning

**What it is:** a computer-vision and OCR pipeline for physical book highlights.

**What it does:** applies image orientation, loads RGB pixels, obtains OCR words and lines through macOS OCR, detects yellow highlighter regions, retains overlapping words, rejects some edge/adjacent-line artifacts, groups words into passages, and joins broken line-ending hyphenation.

**Core output:** passage text, bounding boxes, minimum OCR confidence, file hash, blur/glare measurements, and a retake flag. Word-box approximation is available if word-level OCR yields nothing but line OCR succeeds. Detection is specifically for yellow highlights; this is not a general photograph-to-full-document transcription system.

Blur, glare, and low-confidence ratios can flag a retake. No detected passages also forces retake review. The reviewer can edit passages/page number, approve, discard, or mark a photo for retake. Retake photos are parked in `_retake`; stored paths follow moves.

### 3. Book identification

**What it is:** metadata lookup and a book-folder identity gate.

**What it does:** reads cached `.book.json`, otherwise uses `book.txt` or the folder name as a query. It tries Open Library and Google Books, records matching confidence, and caches the result. Human correction/confirmation can settle uncertain metadata, rename the folder to a title slug, and update stored image paths.

**Separate capability:** `find_cover` can inspect photos in capture-time order and ask a gateway profile to identify/read a cover. This helper exists, but the production coordinator constructs `ImageExtractor` with `metadata_client=None`, and the active `load_or_resolve` path uses a text query. Automatic cover classification is not wired into the normal coordinator run.

### 4. Text cleanup and human correction

**What it is:** two different correction mechanisms.

**Automatic OCR repair:** the photo extractor can ask a local gateway provider to fix optical recognition mistakes. A normalized edit-distance guard rejects excessive changes (default fraction 0.15) and retains the raw passage in that case. Gateway failures raise an error. The coordinator enables this repair; the standalone image extractor defaults to leaving it off.

**Human cleanup review:** abbreviation expansion runs first, then spelling suggestions. Abbreviations come from saved shorthand/expansion mappings, with literal matching, optional case sensitivity, word-boundary checks, and deterministic overlap resolution. Spelling suggestions come from a local model, then Python validates the location, single-word form, edit distance, protected regions, and duplicates.

Review actions include apply once, apply and remember, skip, accept/reject spelling, previous/next, and continue when the phase is settled. “Remember” retains a mapping; it does not bypass future human occurrence review. Code, frontmatter, URLs, emails, link targets, and path-like spans are protected from cleanup suggestions. Revised drafts remain in memory until final approval; mapping records and the cleanup audit log are durable. A restart rebuilds cleanup rather than restoring the exact interaction position.

### 5. Obsidian publishing and source archiving

**What it is:** the output layer for accepted intake text.

**What it does:** writes ordinary text notes to the vault root and scanner notes beneath `Page Scanners/<book-slug>`. It chooses an available filename instead of overwriting an existing note. Photo notes carry book/page information, passage markers, and links to archived images.

Approved photo passages also accumulate in one `<book-slug>-highlights.md` document per book. Page markers make repeated append attempts idempotent. The accumulated document is later read back into explicit selections, preserving passage identity and provenance.

The coordinator records publication before moving the original, then records completion. On a later run it can finish an interrupted recorded move without republishing the note. Photos archive under `Database/page_scanner_photos/<book-slug>`; other files use a configured archive root or `Database/intake_processed`.

### 6. Obsidian and Markdown source collection

**What it is:** source adapters that feed captured text into the pipeline.

**What it does:** discovers a vault from Obsidian's configuration when none is specified, finds Markdown notes recursively, and applies include/exclude globs. Current defaults exclude `.obsidian`, `.trash`, `Notion`, and `Readwise`. Unreadable or malformed ordinary notes are logged and skipped so other notes can be captured.

Scanner notes and accumulated book-highlight documents are excluded from ordinary whole-note capture. `capture_book_highlights` reads the accumulated book documents, builds a parent per photographed page, and supplies explicit sibling passage selections. Page identity is included in captured text so identical quotes from different pages remain distinct.

`capture_markdown_tree` separately supports a generic Markdown folder. It is a standalone adapter and has simpler failure behavior than the Obsidian scanner.

### 7. Immutable capture, normalization, deduplication, and versioning

**What it is:** the durable record of text entering knowledge ingestion.

**What it does:** validates UTF-8, rejects NUL bytes/malformed frontmatter, extracts simple frontmatter metadata, normalizes line endings/Unicode/spacing/bullet markers, canonicalizes origins, and hashes both raw and normalized content.

Exact-byte repeats attach another capture to an existing source record. Normalized-equivalent content shares a canonical record. New content at an existing source origin creates a version that supersedes its predecessor. Raw captured text and initial envelope JSON are published as immutable files; later processing rechecks recorded hashes. Missing/changed raw content is quarantined.

“Raw capture” here means the text handed to `pipeline.capture`. For a PDF or photo intake, that text comes after conversion and Obsidian publication. The original binary document/photo is archived separately; the core capture method itself expects UTF-8 text, not arbitrary PDF or image bytes.

### 8. Meaningful passage segmentation

**What it is:** a parser that turns documents into exact source highlights.

**What it does:** passes short documents through as one highlight, or scans larger documents in bounded windows and asks a model whether a new broad topic begins at an offered boundary. The model chooses a boundary ID; Python slices the original normalized text and checks coverage.

Defaults: pass-through at 40 words or fewer; inspection target 500 words; profile `document-segmentation-v1`, pinned to provider `phi4-local` and model `phi4:14b-q4_K_M`; one attempt per window. These are inspection windows, not a guarantee that every resulting highlight has a 500-word maximum. Surrounding context defaults to three sentences before and after, stored separately from evidence.

Supplied user selections bypass semantic segmentation. A deterministic heading-based segmenter also exists for explicit offline/test use. Production failures remain pending; there is no silent fallback to heading segmentation. Parsed boundaries are persisted so retries keep stable highlight identities.

### 9. Semantic knowledge extraction

**What it is:** structured LLM extraction from one or several highlights.

**What it does:** requests concepts, claims, relations, field tags, quality signals, and model-reported confidence using the external gateway profile `knowledge-extraction-v1`. The default pipeline groups four pending highlights into one extraction call, including highlights from different documents.

Python validates the returned schema and locates evidence quotes by exact string search within the relevant highlight. Unsupported quotes are dropped rather than assigned guessed positions. Proposal IDs are scoped by highlight so siblings do not collide. Extraction failure leaves that batch pending; other batches can proceed. Saved envelopes let dispatch retry without another extraction call.

The gateway profile determines the actual extraction provider/model; that service's configuration is not present here. `EmptySemanticExtractor` is an offline fallback for direct pipeline construction: it emits no knowledge and forces review. The production runner installs `GatewayExtractor`.

### 10. Evidence checks and knowledge review

**What it is:** deterministic review rules plus human proposal decisions.

**What it does:** flags low overall/proposal confidence (default threshold 0.75), missing/mismatched/ambiguous evidence, invalid offsets, quality signals, empty extraction, and alias/identity proposals. Photo-derived highlights always require semantic review, even after OCR approval.

Clear results can proceed automatically. Flagged results enter durable review queues. Review supports approve, reject, or edit per proposal and retains originals, final versions, resolver, notes, and timestamps. The coordinator exposes source highlight/context, sibling proposals, and photo evidence where available. Downstream dispatch waits for an accepted envelope.

The pipeline's separate `highlight_cleanup` hook still defaults to `NoHighlightCleanup`, which returns no suggestions. Intake cleanup is implemented, but abbreviation/spelling cleanup of existing ordinary Obsidian highlights is not connected through this hook by the production runner.

### 11. Three downstream stores


| Store                 | What it contains                                                                 | Core functionality                                                                                                                     |
| --------------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| SQLite content store  | Sources, acquisitions, highlights, comments, transformations, claims, tags       | Structured content/provenance records; stable IDs; accepted relation triples and free-text claims; deletion of predecessor projections |
| Neo4j knowledge graph | Concepts, relations, evidenced claims, identity proposals/links, cycle conflicts | Graph writes, name lookup, neighbors, reachability, identity-aware retrieval, temporal claim fields, contribution tracking             |
| Chroma vector store   | Embedded chunks of accepted highlights plus provenance metadata                  | Semantic similarity search, metadata/document filtering, direct retrieval, batch upsert, source deletion                               |


The graph consumer creates/resolves nodes needed by accepted relations and claims. It does **not** independently iterate all standalone `ConceptProposal` objects, so an isolated extracted concept is not guaranteed its own graph node. Claims need both evidence and concept labels to project; relations need evidence. Cyclic relations explicitly marked hierarchical are diverted into `CycleConflict` records rather than written as ordinary edges.

The graph supports reviewed alias/same-as links and lexical identity proposals. Stable/domain-scoped IDs also allow repeated use of a normalized label in the same domain to land on the same node. This does not amount to a complete semantic disambiguation system. Graph identity/cycle review capabilities are separate from the cockpit's semantic-proposal review endpoints.

Vectorization uses `nomic-embed-text`, 768 dimensions, through the gateway's `ollama` provider. It checks provider, model, dimension, and finite numeric vector values. Default chunks target three sentences, one sentence of overlap, a 150-word ceiling, and an 8,000-character ceiling; oversized sentences may be hard-split. Fragment selections may use a supplied containing sentence for search while retaining the selected fragment as evidence. The older character-based `chunk_text` helper also remains, but the active consumer uses `sentence_chunks`.

The content schema has a comment table and insertion API, but current automatic projection does not generate comments. Machine field tags are stored as system-derived tags.

### 12. Dispatch, retry, orchestration, and reporting

**What it is:** the control layer that sequences ingestion and tracks completion.

**What it does:** only dispatches approved/no-review-needed envelopes, intersects registered consumers with an allowed-consumer list, skips completed writes, records failures per target, and retries saved accepted envelopes. Defaults permit `kg`, `sqlite`, and `vector`. Source type describes provenance; it does not determine routing.

The full coordinator runs: preflight → intake discovery → per-item gates/publication → intake handoff decision → Obsidian capture → pending parsing/extraction → semantic proposal review → dispatch retry → report. After intake work, the user can continue into knowledge ingestion or stop after intake. A process lock prevents competing coordinator runs; stage transitions and matching decision identities/revisions guard navigation and stale submissions.

Preflight checks configuration, writable/storage paths, SQLite, Obsidian, Neo4j, gateway profiles/embeddings, segmentation model, and relevant local cleanup/OCR/conversion dependencies. Production sessions require strict Neo4j preflight. These checks can create directories/schemas and perform probes; they are not completely read-only.

Reports record stages, intake outcomes, captures, processing/review/dispatch counts, and errors. Existing captures, parses, review decisions, and projections survive restarts, but the active coordinator object and cleanup interaction draft are in memory. Recovery is durable-work-based, not restoration of the complete live run state. Writes to all three downstream stores are not one distributed transaction: partial projections are possible and repaired through recorded retries.

### 13. Cockpit API

**What it is:** a FastAPI router and typed review contract for an external UI.

**What it does:** serializes mutations on one worker, exposes the latest run snapshot, rejects busy/stale operations, serves review photo evidence, provides reports, and manages abbreviation mappings independently of active runs.

Router-relative endpoints: `GET /run`, `POST /run/start`, `POST /run/decision`, `POST /run/retry`, `GET /run/{run_id}/report`, `GET /evidence/{run_id}/{item_id}`, and GET/POST/PATCH/DELETE operations under `/cleanup/mappings`.

The module describes mounting under `/api/ingestion` by an external AI OS gateway. This folder contains no visual cockpit frontend, no FastAPI application instance, and no standalone server entry point that mounts the router.

## File-by-file map

Paths below are relative to `merged-ingestion`. Unless prefixed otherwise, Python paths are beneath `src/ingestion/`.


| File                                        | What it is / core responsibility                                                                          |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `config.py`                                 | Path resolution, shared environment discovery, segmentation/chunk/intake settings and validation          |
| `models.py`                                 | Validated capture, selection, evidence, proposal, envelope, access, review, and outcome contracts         |
| `ids.py`                                    | Shared deterministic source-independent utility IDs, highlight IDs, and domain-scoped concept IDs         |
| `normalization.py`                          | UTF-8 validation, simple frontmatter parsing, structural text/origin normalization, hashes                |
| `parsing.py`                                | Boundary selection, exact highlights, surrounding context, selection handling, coverage validation        |
| `pipeline.py`                               | Capture → persisted parse → batched extraction → envelope/review → dispatch; review/retry methods         |
| `store.py`                                  | Ingestion SQLite ledger, captures/versions/parses/highlights/envelopes/review items/dispatches/quarantine |
| `review_policy.py`                          | Confidence, evidence, quality, and identity-related review signals                                        |
| `routing.py`                                | Default consumers and intersection of allowed and registered targets                                      |
| `dispatch.py`                               | Approval-aware, target-by-target delivery with completion/failure records                                 |
| `runner.py`                                 | Production store/extractor composition; reusable session; vault or explicit text-document runs            |
| `content_store.py`                          | Seven-table relational content schema and envelope projection/deletion APIs                               |
| `intake/base.py`                            | Extractor protocol, shared intake output, basic empty/suspicious text checks                              |
| `intake/funnel.py`                          | Drop-folder scan, extractor selection, prepared result, note publication and original move helpers        |
| `intake/extractors/markdown_passthrough.py` | UTF-8 Markdown input                                                                                      |
| `intake/extractors/pdf.py`                  | Page text-layer extraction and OCR fallback                                                               |
| `intake/extractors/word.py`                 | DOCX paragraphs, styles, lists, tables, embedded-image warnings                                           |
| `intake/extractors/legacy_word.py`          | DOC conversion and structural-loss review flags                                                           |
| `intake/extractors/image.py`                | Photo processing plus optional OCR repair and book metadata in one intake result                          |
| `sources/markdown_tree.py`                  | Generic recursive Markdown capture adapter                                                                |
| `sources/obsidian.py`                       | Vault discovery, filters, ordinary-note capture, and book-passage selections                              |
| `sources/book_metadata.py`                  | Book API lookups, metadata cache, optional cover classifier, correction/confirmation and folder naming    |
| `sources/page_scanner/images.py`            | Image decoding/HEIF support, EXIF orientation and original-file hashing                                   |
| `sources/page_scanner/detect.py`            | HSV-based yellow-highlight mask                                                                           |
| `sources/page_scanner/ocr.py`               | macOS word/line OCR adapters and approximate word-box fallback                                            |
| `sources/page_scanner/quality.py`           | Blur/glare/confidence quality gate                                                                        |
| `sources/page_scanner/photo_pipeline.py`    | Highlighted-word selection, passage grouping, boxes/confidence and photo result                           |
| `sources/page_scanner/cleanup.py`           | Local LLM optical-error repair guarded by text difference                                                 |
| `sources/page_scanner/store.py`             | Page/passage SQLite, parked reviews, status/edit updates, image paths and retake moves                    |
| `text_cleanup/models.py`                    | Cleanup passage/candidate types, replacement recomputation and updated offsets                            |
| `text_cleanup/abbreviations.py`             | Literal shorthand matching outside protected spans                                                        |
| `text_cleanup/protected.py`                 | Detects regions excluded from cleanup                                                                     |
| `text_cleanup/spelling.py`                  | Local model spelling suggestions and deterministic acceptance checks                                      |
| `text_cleanup/working.py`                   | Per-item draft, phase order, occurrence navigation, decisions and revision counters                       |
| `text_cleanup/store.py`                     | Durable abbreviation mappings and cleanup audit records                                                   |
| `publish/vault_writer.py`                   | Note creation, page formatting, accumulated book passages and approved publication/archive helpers        |
| `extraction/base.py`                        | Single/batch extractor interfaces and empty offline extractor                                             |
| `extraction/prompts.py`                     | Knowledge extraction instructions and single/batch prompt rendering                                       |
| `extraction/gateway.py`                     | Gateway chat calls, response schema validation and verbatim evidence lookup                               |
| `consumers/content_consumer.py`             | Adapter from accepted envelope to `ContentStore`                                                          |
| `consumers/kg_consumer.py`                  | Accepted claims/relations → graph; predecessor purge, identity proposals and cycle conflicts              |
| `consumers/vector_consumer.py`              | Accepted highlight → verified text → sentence chunks → embeddings/Chroma metadata                         |
| `kg/models.py`                              | Graph nodes/edges, temporal claims, identity links/proposals and conflicts                                |
| `kg/identity.py`                            | Normalized concept labels and external identifier keys                                                    |
| `kg/errors.py`                              | Distinct configuration/unavailable/schema/read/write exceptions                                           |
| `kg/kg_store.py`                            | Neo4j preflight, constraints, writes, contribution purging, identity review and graph query APIs          |
| `vector/chunking.py`                        | Sentence-aware production chunker, coverage checks, and older character chunking helper                   |
| `vector/vector_store.py`                    | Persistent Chroma wrapper, embedding validation, collection profiles, search/get/delete/upsert            |
| `coordinator/coordinator.py`                | Full sequential run owner, intake gates, publication recovery, knowledge review and terminal reports      |
| `coordinator/gates.py`                      | Book identity, cleanup, content approval and phase-handoff gates                                          |
| `coordinator/preflight.py`                  | Aggregated dependency/configuration/storage readiness checks                                              |
| `coordinator/state.py`                      | Run/pending-decision views, process lock and durable publication records                                  |
| `coordinator/stages.py`                     | Legal run stages/statuses and transition checks                                                           |
| `coordinator/report.py`                     | JSON report read/write and newest-report lookup                                                           |
| `coordinator/errors.py`                     | Busy/no-active-run/illegal-decision/transition/preflight/gate exception types                             |
| `coordinator/__init__.py`                   | Public start/advance/decision/retry/report API; active coordinators held in process memory                |
| `cockpit/server.py`                         | HTTP review service, typed frontend payloads, evidence serving, environment config and mapping endpoints  |
| `scripts/bootstrap_environment.sh`          | Non-editable `uv` installation and immediate import verification                                          |
| `scripts/run.sh`                            | Executes supplied commands with `uv run --no-sync`; not an ingestion-specific CLI                         |
| `scripts/verify_environment.py`             | Verifies installed module locations and absence of editable ingestion installation markers                |
| `scripts/configure_local_neo4j.py`          | Configures a generated Neo4j password and shared environment settings; setup utility, not part of intake  |
| `config/obsidian_filters.txt`               | Editable note inclusion/exclusion rules                                                                   |
| `pyproject.toml`                            | Python/build/runtime dependencies, local gateway source, pytest/mypy configuration                        |
| `uv.lock`                                   | Resolved dependency lockfile                                                                              |


The remaining `__init__.py` files are package boundaries or convenience exports: `cockpit`, `consumers`, `intake`, `intake/extractors`, `kg`, `publish`, `sources`, `sources/page_scanner`, `text_cleanup`, and `vector`. They add no separate product workflow; `coordinator/__init__.py` is the substantive exception listed above.

## Where data goes

Paths are relative to the configured database root unless otherwise stated.


| Location                                       | Purpose                                                                                        |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `raw/`                                         | Immutable captured text bytes                                                                  |
| `envelopes/`                                   | Immutable initial extraction-envelope JSON artifacts; later review state is retained in SQLite |
| `sqlite/ingestion.db`                          | Capture/parse/extraction/review/dispatch ledger                                                |
| `sqlite/content.db`                            | Accepted relational content projection                                                         |
| `sqlite/processed.db`                          | Scanner pages/passages and parked intake approval state                                        |
| `sqlite/text_cleanup.db`                       | Abbreviation mappings and cleanup audit                                                        |
| `sqlite/coordinator.db` and sibling lock file  | Publication recovery records and coordinator exclusion                                         |
| `neo4j/`                                       | Expected Neo4j data location checked in strict mode                                            |
| `chroma/`                                      | Persistent vector index                                                                        |
| `reports/`                                     | Run JSON reports                                                                               |
| `page_scanner_photos/<book-slug>/`             | Archived original book photos                                                                  |
| `intake_processed/` or configured archive root | Archived original non-photo inputs                                                             |
| Obsidian vault                                 | Published notes and accumulated book highlights                                                |
| Book folder `.book.json`                       | Cached book identity metadata                                                                  |




## What remains incomplete or external

1. **External LLM gateway:** package/service ownership lives elsewhere. `pyproject.toml` points to `../../llm_gateway`; that path resolves to `AI OS/llm_gateway`, which was absent during this review. An already installed gateway package may exist, but this checkout alone does not supply it. [THIS IS COMPLETE, CODEX THINKS IT ISNT BECAUSE I HAVE MADE A COPY FO THE ORIGINAL VERSION OF THE CODE THAT WASNT CONNECTED INSTEAD OF BREAKING THE WORKING CODE RIGHT NOW] 
2. **Old parent-directory assumptions:** default database/shared `.env` discovery looks for a parent named `AI Code`. This checkout is under `AI OS`, so configure `INGESTION_DATABASE_ROOT` and process environment explicitly or update those assumptions. The credential setup script specifically requires an `AI Code` parent. [FIXED] 
3. **No complete UI/application host:** the cockpit router is present; its visual frontend and external application mount are not. [NEEDS TO BE DONE] 
4. **No scheduler/watch daemon:** the code performs bounded runs on invocation. No continuous drop-folder watcher or scheduling component remains here. [NEEDS TO BE DONE] 
5. **No tests in this folder:** pytest configuration and test-oriented comments remain, but no test suite was present. This catalog does not certify end-to-end runtime behavior. [THATS FINE, I DELETED THEM, BECAUSE I WILL BE REPLACING MOST OF THIS] 
6. **Separate graph administration:** graph identity links, temporal claim linking, traversal and cycle-conflict records exist at the store level; the cockpit router does not expose a complete graph administration UI/API. [BY DESIGN WILL BE REPLACED BY PULLING MORE FRAMEWORKS] 
7. **Existing-note cleanup hook:** intake cleanup works; the separate per-highlight pipeline cleanup hook remains a no-op by default. [FRAMEWROKS IMPORTED WILL HELP HERE] 
8. **Some schema/helper capabilities exceed active projections:** comment insertion, standalone concept writes, cover recognition, generic Markdown scan and legacy chunking exist, but are not all exercised by the default coordinator. [THATS FINE WE WILL GET RID OF THEM FOR NNOW] 



## Examples of the intended behavior

**A dropped DOCX:** text/structure are converted to Markdown; cleanup suggestions are reviewed if present; extraction issues may require final text approval; a note is written and the original archived. After the intake handoff, the note is captured, segmented and mined for knowledge. Accepted results reach all permitted stores.

**A highlighted book photo:** yellow passages are OCR'd and optionally repaired; book identity and cleanup are settled; the reviewer edits/approves or chooses retake/discard. Approved passages accumulate in the book document and the original photo is archived. During knowledge ingestion, those passages keep their explicit selection boundaries and photo provenance, and semantic proposals require review.

**An edited Obsidian note:** its new captured text version supersedes the earlier one. New accepted envelopes cause consumers to remove predecessor projections/contributions and write replacements. The capture ledger retains the original history; downstream projections are refreshed independently.