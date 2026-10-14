# Ingestion: How It Flows Today, and How I'd Break It Up

This doc gives you three things:

1. the whole system on one page, as it actually runs today
2. what's tangled
3. my recommended breakup, which is a **move, not a rewrite** (decision
   M2 in `00-DECISIONS.md`)

The detailed step-by-step plan is `01-reader-writer-boundary-refactor.md`.

All code paths are under `gateway/src/gateway/ingestion/` unless they say
otherwise. Line counts and line numbers were checked on 2026-10-13. The
ingestion code is about **16,500 lines**, with **460 tests** (as collected by pytest on 2026-10-13) in
`gateway/ingestion_tests/`.

---

## 1. The flow today, in 10 steps

One "run" goes through these stages in order. The stage names come from
`coordinator/stages.py`.

| # | Stage | What happens | Main code |
| --- | --- | --- | --- |
| 1 | **Preflight** | Check the databases and the AI gateway are reachable | `coordinator/preflight.py` |
| 2 | **Find dropped files** | Look in the drop folder (your Desktop) for new files and photos | `intake/funnel.py`, `config.py` |
| 3 | **Intake checks, one file at a time** | Each file is turned into text (PDF, Word, photo OCR). Then it passes through the checks: book identity (photos), abbreviations, spelling, and your approve click. | `intake/extractors/`, `sources/page_scanner/`, `coordinator/gates.py`, `text_cleanup/` |
| 4 | **Write files into your vault** | Each approved file is written into your Obsidian vault as a note. **This is how dropped files join the main flow: they become Obsidian notes.** | `publish/vault_writer.py` |
| 5 | **Barrier** | Wait until every dropped file is done | `coordinator/coordinator.py` |
| 6 | **Read the vault** | Walk the vault and save every new or changed note as a "source record". The filter file decides what's skipped, and it's missing today (finding F1). | `sources/obsidian.py`, `pipeline.py` `capture()`, `normalization.py`, `ids.py` |
| 7 | **Split and extract** | Split each note into highlights, sometimes with an AI deciding where topics change. Then the extractor AI pulls concepts, claims and links out of the highlights, 4 highlights per call. | `parsing.py`, `extraction/`, `pipeline.py` `parse_source()` / `process_pending()` |
| 8 | **Flag check** | Plain-code rules decide whether a highlight is "all clear" or "needs you" | `review_policy.py`, called from `pipeline.py:456` |
| 9 | **Fact review** | Flagged facts wait for you, one fact at a time. Each decision is saved, and the highlight is published once all its facts are decided. | `store.py` (review tables), `coordinator.py` `_pending_proposal()` / `submit_decision()`, `pipeline.py:745` |
| 10 | **Write to the stores** | Approved facts go to the knowledge graph, vector store and content database. A failed destination is retried on its own. | `dispatch.py`, `routing.py`, `consumers/`, `kg/`, `vector/`, `content_store.py` |

**Around all of this:**

- **The ledger** (`coordinator/state.py`, `stages.py`) records every step so
  a crash resumes in the right place. It is **moved, never rewritten**.
- **The API and UI** (`server.py`) let the shell app start runs, show what's
  waiting and send your decisions.

---

## 2. The pieces, and how big they are

| Piece | Files | Lines | Tests today |
| --- | --- | --- | --- |
| Obsidian and folder readers | `sources/obsidian.py`, `sources/markdown_tree.py` | ~300 | Yes (`test_sources_obsidian`, `test_sources_markdown`) |
| Page scanner (photos) | `sources/page_scanner/` (8 files), `intake/extractors/image.py` | ~1,300 | Yes (`test_page_scanner`) |
| Book identity | `sources/book_metadata.py` | 485 | Yes (`test_book_metadata`) |
| Drop-folder intake and file readers | `intake/` (funnel, PDF, Word, markdown) | ~860 | Yes (`test_intake_funnel`) |
| Text cleanup (abbreviations, spelling) | `text_cleanup/` (7 files) | ~1,150 | Yes (5 test files) |
| Intake checks (gates) | `coordinator/gates.py` | 734 | Yes (`test_cleanup_gate`, `test_coordinator`) |
| Capture (saving source records) | `pipeline.py` `capture()`, `normalization.py`, `ids.py` | ~360 | Yes (`test_pipeline`, `test_normalization`, `test_ids`) |
| Splitting into highlights | `parsing.py` | 884 | Yes (`test_parsing`) |
| Fact extraction | `extraction/` (3 files), plus part of `pipeline.py` | ~620 | Yes (`test_extraction_gateway`) |
| Flag rules ("all clear") | `review_policy.py` | 206 | **No test of its own.** Only covered indirectly through the pipeline. |
| Ingestion database | `store.py`, `models.py` | 1,270 | No test of its own (`IngestionStore` isn't named in any test). Covered through the pipeline and coordinator tests. |
| Graph writer | `kg/` (4 files), `consumers/kg_consumer.py` | ~2,090 | Yes (`test_kg_store`, `test_kg_consumer`) |
| Vector writer | `vector/` (2 files), `consumers/vector_consumer.py` | ~750 | Yes (3 test files) |
| Content database writer | `content_store.py`, `consumers/content_consumer.py` | ~585 | Yes |
| Vault writer | `publish/vault_writer.py` | 519 | Yes (`test_vault_writer`) |
| Sending to destinations | `dispatch.py`, `routing.py` | ~100 | Yes (`test_routing`, plus indirect) |
| Run coordinator and ledger | `coordinator/` (`coordinator.py`, `state.py`, `stages.py`, `preflight.py`, `report.py`, `errors.py`) | ~2,020 | Yes (`test_coordinator`, `test_kg_preflight`) |
| Runner | `runner.py` | 301 | Yes (`test_runner`) |
| API for the UI | `server.py`, `routes.py`, `setup.py` | ~820 | Yes (`test_cockpit_server`, `test_wire_contract`) |
| UI preview fake data | `preview.py` | 226 | Used by `cockpit_preview.py` |
| AI access | `http_client.py`, plus separate "chat client" definitions in 4 places | — | Partly |

---

## 3. What's tangled (why you feel it's bloated)

1. **`pipeline.py` does five jobs in one class.** It saves sources,
   splits notes, calls the extractor, runs the flag rules and settles
   reviews. `parse_source()` alone is about 300 lines (336–647).
2. **`coordinator.py` is 1,372 lines.** One function, `view()`, is about
   **600 lines** (215–831). It builds every kind of "what's waiting for
   you" screen in one place.
3. **`store.py` (910 lines) holds every table:** sources, parses,
   highlights, reviews, deliveries and quarantine, all in one class.
4. **`server.py` (772 lines) is mostly about 45 data shapes** for the UI,
   mixed in with the routes and the settings loader
   (`config_from_environment`).
5. **Four separate ways to call the AI.** Each of these defines its own
   "chat client":
   - `extraction/gateway.py:45`
   - `parsing.py:110`
   - `runner.py:42`
   - `text_cleanup/spelling.py`

   Adding Opus 5.5, or the Batch API, means touching all four.
6. **Fake UI preview data (`preview.py`) sits inside the real code.**
7. **Readers and writers are mixed in with the pipeline.** Plan 01 already
   noticed this.

---

## 4. My recommended breakup

**The principle:** one folder per job. Each folder has one clear way in.
Behaviour doesn't change. The database files and their tables don't
change. The UI's API doesn't change.

```text
ingestion/
  sources/              READERS: "here's what I found"
    obsidian/             obsidian.py (+ the restored filter file)
    folders/              markdown_tree.py, intake funnel, PDF/Word/markdown readers
    page_scanner/         photo pipeline, OCR, quality, book identity
  intake_gates/         THE CHECKS BEFORE FACTS (one file per gate)
    book_identity.py, cleanup.py, content_approval.py, phase_handoff.py
    text_cleanup/         unchanged inside
  capture/              saving source records: capture(), normalization, ids
  segmentation/         parsing.py, split into "where do topics change" and "cut into highlights"
  extraction/           the extractor AI (+ the extraction part of parse_source)
  review/               flag rules (review_policy.py), the review queue, settling decisions
    (empty slot for the judge; nothing built yet)
  destinations/         WRITERS: "I know how to store it there"
    knowledge_graph/      kg/, kg_consumer
    vector_store/         vector/, vector_consumer
    content_database/     content_store, content_consumer
    obsidian_vault/       vault_writer
    dispatch.py           sending + per-destination retry (+ routing.py)
  llm/                  ONE way to call the AI (replaces the 4 separate ones)
  storage/              store.py split by table group: sources, parses, reviews, deliveries
                        (same SQLite file, same tables)
  coordinator/          the run itself
    stages.py, state.py   LEDGER: moved as-is, never edited
    coordinator.py        split: advancing the run, building each waiting screen, taking decisions
  api/                  server.py split: routes, data shapes, settings loader
  pipeline.py           becomes thin: capture → split → extract → review → dispatch
```

`preview.py` moves out of the real code, next to the tests.

**Slots, not features.** Because the breakup now comes first (M1), the
judge and batching don't exist yet. The structure leaves room for them:
`review/` for the judge, `llm/` for the Batch API. **Nothing new is built
during the breakup.**

---

## 5. The order of moves (the principle)

**Start with the best-tested and least connected pieces. The coordinator
goes last.**

1. **Safety net first.** Record today's results for all 460 tests (as collected on 2026-10-13). Add
   "pinning" tests for the pieces with no test of their own (flag rules,
   ingestion database) before anything moves.
2. **Writers** (`destinations/`). They're well tested and have few
   connections.
3. **Readers** (`sources/`), including fixing where the filter file lives.
   The fix itself is logged as a separate step.
4. **Flag rules and the review queue** (`review/`).
5. **Capture, splitting and extraction out of `pipeline.py`.**
6. **Split `store.py`** into `storage/`.
7. **One AI access path** (`llm/`). This also prepares the gateway models
   and Batch API work.
8. **Split `server.py`** into `api/`. The UI's API file (`openapi.json`)
   must come out identical.
9. **Split `coordinator.py`.** The ledger files are moved, not edited.
10. **Move `preview.py` out**, and remove the temporary old-path imports.

---

## 6. What "targeted checks" means here

For **every** move:

1. **Before:** write or confirm a small test that pins what this piece
   does **today**, run on its own.
2. **Move:** one piece, one step. Old import paths keep working until the
   final cleanup step.
3. **After:** that piece's test passes unchanged, **and** the full test suite (460 tests on 2026-10-13)
   passes unchanged.
4. **No fixes inside a move.** Bugs found during a move are written into
   the component's review doc and fixed in their own separate step.
   Otherwise you can't tell whether the move itself broke something.
5. **Proof the edges didn't change:**
   - `openapi.json` is unchanged
   - the database tables are unchanged
   - `coordinator/stages.py` and `state.py` have only moved, not changed

---

## 7. Component reviews (one per piece, before it moves)

Each piece gets a review doc in `component-reviews/`, written in a fresh
chat (prompt P2 in `FRESH-CHAT-PROMPTS.md`). Every review answers the
same questions:

- how it works now
- where it sits in the code
- what it was designed to do
- what the rest of the code expects of it
- its tests and the gaps in them
- the targeted checks to add before the move
- where it lands in the breakup

| Review | Piece |
| --- | --- |
| CR-01 | Obsidian and folder readers |
| CR-02 | Page scanner and book identity (includes the "every photo is flagged" one-pager) |
| CR-03 | Drop-folder intake and file readers |
| CR-04 | Intake checks and text cleanup |
| CR-05 | Flag rules / "all clear" (this **is** the review-policy one-pager you asked for) |
| CR-06 | Capture and splitting into highlights |
| CR-07 | Fact extraction |
| CR-08 | Ingestion database and review queue |
| CR-09 | Writers: graph, vector, content, vault, and dispatch |
| CR-10 | Run coordinator, ledger, runner and API |
| CR-11 | AI access (the 4 chat clients → one) |

## Aryaman's comments

