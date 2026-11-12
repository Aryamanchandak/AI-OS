# Corpus Convergence Changes

## Overview

The convergence work moves corpus ingestion toward three capture paths meeting at `Raw Data/lib/capture.py::capture()`: Obsidian notes, mutable processing items, and Page Scanner highlights. Bronze files remain the immutable captured layer, and review/correction happens before bronze in `Raw Data/processing/`. In the current workspace, Obsidian review items do converge through `capture()` after pre-bronze review; Page Scanner still has legacy/out-of-phase direct bronze publishing code and has not yet been converted to the same capture-only path.

## Phase 1 - Inbox And Processing Claiming

`Raw Data/lib/obsidian_sync.py` mirrors Obsidian files into `Raw Data/inbox/` and claims feeder files into `Raw Data/processing/`. Working files are named deterministically from the source stem plus a 16-character SHA-256 fingerprint of the resolved source path, so processing identity is based on source path / working path, not `content_hash`.

No-change re-runs skip byte-identical files. Existing matching working files are skipped, and byte-identical duplicates already in `processing/` are also skipped.

## Phase 2 - Review Surface

`Raw Data/lib/review.py` lists mutable processing files, reads and saves editable text, classifies whether image review is needed, and approves reviewed text into capture. It keeps all edits in `processing/` until approval, then calls `capture()` and records lineage for Obsidian-derived notes.

## Phase 3 - Image Placeholder Review

`Raw Data/lib/images.py` detects images in processing items, inserts numbered placeholders, stores sidecar manifests, and blocks final approval while placeholders remain unresolved. Placeholder state is keyed by working file path plus placeholder index through the `.images.json` sidecar beside the processing file; it is not keyed by `content_hash`.

## Phase 4 - Glossary Expansion

`Raw Data/lib/review.py` adds glossary support in `glossary(shorthand, expansion, updated_at)`. Expansion uses a word-boundary regex, `r"\b" + re.escape(shorthand) + r"\b"`, so a mapping such as `dur -> Duration` changes `dur` as a standalone token but does not rewrite `during`.

## Phase 5 - Spellcheck Suggestions

`Raw Data/lib/spellcheck.py` proposes conservative spelling edits through the LLM gateway. The review UI wiring in `Automation Personal/Page Scanner/server.py` presents each suggestion with Accept and Reject buttons. Accept mutates the editor text; Reject removes only the suggestion from the pending list and leaves text unchanged. This UI file is out of scope for Phases 1-6 and is a current-state deviation.

## Phase 6 - Capture And Lineage

`Raw Data/lib/review.py::approve_item()` calls `call_capture(body=body, source=capture_source, authored=True)`. The wrapper then calls `capture(body=..., source=..., authored=...)` if the installed capture signature supports `body`, otherwise it falls back to the current local signature, `capture(source=..., content=body, authored=...)`.

Immediately after a successful Obsidian-derived capture, `record_note_lineage()` inserts `(source_path, content_hash, captured_at)` into `note_lineage`. This is the prerequisite for Phase 7 diff review, although the live `Database/sqlite/ledger.db` currently has zero `note_lineage` rows.

## New Files

| File | Purpose |
| --- | --- |
| `Raw Data/lib/obsidian_sync.py` | Mirrors Obsidian into `inbox/` and claims files into `processing/`. |
| `Raw Data/lib/review.py` | Provides processing review, glossary, approval, capture, and lineage helpers. |
| `Raw Data/lib/images.py` | Detects image references, inserts placeholders, manages image sidecars, and gates approval. |
| `Raw Data/lib/spellcheck.py` | Produces guarded spelling suggestions for mutable processing text. |
| `Raw Data/inbox/` | Mutable mirror/staging area for source files before processing claim. |
| `Raw Data/processing/` | Mutable pre-bronze review area. |
| `Raw Data/CORPUS_CONVERGENCE_CHANGES.md` | This current-state reference. |

## New Tables

```sql
CREATE TABLE glossary(shorthand TEXT, expansion TEXT, updated_at TEXT);
```

`shorthand` is the abbreviation/token to expand. `expansion` is the replacement text. `updated_at` records when that mapping was last confirmed.

```sql
CREATE TABLE note_lineage(source_path TEXT, content_hash TEXT, captured_at TEXT);
```

`source_path` is the original Obsidian source path resolved from the working-file fingerprint. `content_hash` is the ingested-layer identity returned by `capture()`. `captured_at` records when the lineage row was written.

## Conventions

Working-item id: `obsidian_sync.py` names a processing file as `{safe_stem}--{path_fingerprint}{suffix}`, where `path_fingerprint` is the first 16 hex characters of SHA-256 over the resolved source path.

Placeholder key: `images.py` stores image review state in a sidecar named from the working file path, `working_path.name + ".images.json"`, and each placeholder is identified by its integer `index`.

Lineage: after Obsidian-derived approval, `review.py` maps the working-file fingerprint back to `source_path`, calls `capture()`, then inserts `source_path -> content_hash` into `note_lineage`.

## Not Yet Done

Phase 7 is not implemented as a `reingest.py` flow in `Raw Data/lib/`; the file is absent. Phase 7 depends on `note_lineage` being populated by the Phase 6 insert in `review.py::record_note_lineage()`.

Phase 8 is not cleanly untouched in the current workspace: Page Scanner files already contain Raw Data review/publish integration. `Automation Personal/Page Scanner/core/publish.py` still writes bronze directly and updates ledger rows itself instead of calling `capture()`. Completing Phase 8 should route Page Scanner through the same pre-bronze processing and capture path.

Phase 9 has not changed knowledge graph or vector extraction logic in this workspace. It remains future work to call/delete through existing KG/vector interfaces without altering consumer core logic.
