# Storage Architecture — Principles

**Audience:** Claude / Codex working on this system.
**Status:** Authoritative. When implementation detail conflicts with a principle here, the principle wins. If a principle is wrong, change *this file first*, then the code.

---

## The two non-negotiables

Everything else is downstream of these. If a change violates either, it is wrong regardless of how convenient it is.

1. **Bronze is the immutable source of truth.** Raw captured content is written once, read-only, and never modified or deleted by any automation. The databases (KG, vector, SQLite) are *derived artifacts*. They are disposable and rebuildable from bronze. Backup means "rebuild from bronze," never "snapshot the derived store."

2. **Capture is decoupled from ingestion.** Capture is real-time and dumb (an MCP tool drops content into bronze). Ingestion is deferred, batched, and runs when triggered (Automator button). A capture must never block on, or fail because of, a database write. Days of capture with zero ingestion is a valid, healthy state.

---

## Principles

Each: **Rule** / why / what it forbids.

### P1 — Extraction reads from bronze, never from the cleaned copy
The provenance line runs through bronze. Triplet extraction, chunking, and SQLite row construction all read the raw bronze file.
- *Why:* if extraction read a cleaned/spellchecked copy, the graph's true source would be the cleaned layer, and any silent "correction" would put a claim in the graph that doesn't trace to reality. Bronze-being-immutable is worthless if bronze isn't what fed the graph.
- *Forbids:* any pipeline where a transform sits between bronze and an extractor on the provenance-critical path.

### P2 — Cleaning is spellcheck-only, certain-corrections-only, authored-content-only
The only permitted cleaning is spelling correction, applied only to words the checker is certain about, and only to content the user authored themselves (`authored=True` at capture).
- *Why:* the user is both the source and the corrector of their own notes, so a fix can't distort someone else's claim. The cleaned file exists to make *rereading* pleasant, not to improve extraction (modern extraction handles typos fine).
- *Forbids:* grammar rewriting, summarization, "tidying," or any cleaning of third-party captures (email, transcripts, articles). Forbids cleaned output ever feeding an extractor (see P1).

### P3 — The ledger is the single source of truth for processing state
A SQLite ledger records what has been captured and what has been processed into each target. Folder contents are for human browsing; the ledger is what code queries.
- *Why:* "has X been ingested into the KG?" must be answerable by one query, not by walking folders and parsing names. State in two places drifts.
- *Forbids:* inferring processing status from file existence or folder names. Forbids any target (e.g. Neo4j `:Document.status`) tracking its own ingestion state — that's the ledger's job.

### P4 — Dedup is keyed off content hash, not name or date
Every item carries a `content_hash` (sha256 of normalized bronze body). The ledger refuses a second item with the same hash.
- *Why:* the same article arriving via email and via the article pipeline, or a re-downloaded podcast, must be recognized as one thing. Name/date dedup lets duplicates through.
- *Forbids:* using `item_id`, filename, or capture date as the dedup key.

### P5 — Two ID fields, two jobs
- `item_id` — short, human-readable: `{source_code}_{rand4}` (e.g. `gm_x7k2`). For eyeballing folders. Source codes come from a small **fixed registry** (constants file), never improvised per-source.
- `content_hash` — for dedup and provenance (P4).
These are separate columns. They are not interchangeable.
- *Forbids:* encoding meaning into the random suffix, or collapsing the two into one field.

### P6 — Idempotency is mandatory
Every write into every target is safe to repeat. KG uses `MERGE`. Vector uses deterministic chunk IDs and upsert. SQLite uses upsert. The nightly job can crash mid-item and rerun with no duplication or corruption.
- *Why:* deferred batch + button-trigger means re-runs are normal, not exceptional.
- *Forbids:* blind `CREATE`/`INSERT` on the ingest path.

### P7 — Silent failure is the enemy; surface staleness
Because ingestion is button-triggered, "I haven't run it in a while" and "it's broken" must not look identical. The system surfaces a notification when bronze contains items routed to a target that remain unprocessed past a threshold (default 3 days).
- *Why:* the whole personal-OS thesis is knowing when to surface vs stay silent. A backup pipeline that dies quietly is the exact anti-pattern.
- *Forbids:* shipping ingestion without the staleness check.

### P8 — Format follows data type
- **Markdown** for content meant to be read and reasoned over by a human or an LLM → bronze, spellchecked copy.
- **JSONL** for structured records round-tripped by a script → triplets, chunk-with-metadata.
- **Native dump** for a database's own backup → SQLite `.dump` (plain-text SQL), never a hand-rolled serializer.
- *Why:* hand-writing a markdown-table serializer for structured data means writing escaping logic that can break in the most trust-critical layer.
- *Forbids:* MD tables as the storage format for triplets/rows; inventing a backup format when the tool ships one.

### P9 — Intelligence only where it earns its place
- **Claude** — triplet extraction (quality-sensitive reasoning). Batched via the Anthropic Batch API to halve cost; latency is irrelevant at night.
- **Local (Python, no model)** — chunking by structure (paragraphs, timestamps, headers).
- **Local model (`nomic-embed-text`)** — embeddings. (Middle tier: not reasoning, but model choice affects retrieval — don't downgrade casually.)
- *Why:* "free night compute" must mean *same model, batched and latency-relaxed*, not *cheaper, worse model on the quality-sensitive step*.
- *Forbids:* swapping triplet extraction to a local model to save money; letting "chunking is dumb, do it local" leak into "embedding is dumb too."

### P10 — Persist expensive artifacts, regenerate cheap ones
Persist what costs money or time to recreate (triplets — an LLM call). Don't persist what's a cheap deterministic function of bronze. The spellchecked copy is the one exception: it's cheap but persisted anyway, because its only purpose (pleasant rereading) requires it to exist on disk.
- *Forbids:* persisting a generic "cleaned" stage just for pipeline symmetry.

### P11 — Stage count varies per target; the ledger mechanism does not
KG: `bronze → extracted → written` (two stages, because `extracted` persists an expensive LLM artifact — P10). Vector: `bronze → upserted` (**one** stage — chunking is deterministic and embeddings are cheap/local, so nothing intermediate is persisted; a separate `chunked`/`embedded` ledger row would be the exact fake stage this principle forbids, and ChromaDB fuses embed+upsert into one call anyway). SQLite: `bronze → written` (one stage). The *ledger schema* (one row per item/target/stage) is uniform; the *number of stages* is not. The terminal stage per target is declared once in `lib/config.py::TERMINAL_STAGE` and drives the staleness check (P7).
- *Forbids:* inventing a fake intermediate stage for a target just to match KG's shape.

### P12 — Routing is explicit
A declarative `ROUTING` map (`source → set of targets`) decides where each source flows. Not every source generates triplets.
- *Forbids:* a default of "everything goes to everything," which burns extraction compute producing triplets nobody queries.

### P13 — Backup/recovery scripts stay dumb and standalone
Dump, restore, and rebuild scripts do one boring thing each and import nothing from the live ingestion code.
- *Why:* the backup layer must still work when the rest of the system is broken — that's the whole point of it.
- *Forbids:* a recovery script depending on the ingestion package it's meant to recover.

---

## Locked conventions

> **Naming note (reconciled with the shipped code).** The shared core package is `lib`,
> living at `Database/Raw Data/lib/` and imported as `lib.*` (consumers add `RAW_DATA_ROOT`
> to `sys.path`). The data root is the `RAW_DATA_ROOT` env var (`Database/Raw Data/`). The
> ledger is a single SQLite file at `Database/sqlite/ledger.db`. Earlier drafts of this doc
> and `IMPLEMENTATION_PLAN.md` called these `storage_core`, `STORAGE_ROOT`, and
> `_ledger.sqlite` at the bronze root — those names are historical; the layout below is real.

### Folder layout
```
Database/
  Raw Data/                             # RAW_DATA_ROOT
    lib/                                # the shared core: ledger, capture, ids, paths,
                                        #   heartbeat, bronze, config
    bronze/
      2026-06-30/
        note/
          bronze/   nt_ln2n.md          # read-only (0444), frontmatter + verbatim body
          triplets/ nt_ln2n.jsonl       # persisted KG extraction artifact
          spellcheck/ nt_ln2n.md        # only if authored=True (deferred)
    backups/
      ledger_2026-07-01.sql             # sqlite .dump output
  sqlite/
    ledger.db                           # the ledger — single file, all dates
  knowledge-graph/                      # KG consumer (Neo4j)
  vector-db/
    chroma_store/                       # derived vector store — disposable, rebuildable
```
- **Date → source → stage.** Browsing "what came in from a source today" is one `cd`; all stages of one item share the filename stem.
- **Immutability is enforced at the file, not the folder:** the capture tool writes each bronze file `chmod 0444`. Scattered `bronze/` folders don't weaken this — the file itself rejects writes.
- The ledger lives once at `Database/sqlite/ledger.db`, never per-day. Derived stores (Neo4j, `chroma_store/`) are disposable and rebuildable from bronze.

### Source registry (example — fill with real codes)
```python
SOURCE_REGISTRY = {
    "gm": "gmail",
    "pc": "podcast",
    "ar": "article",
    "nt": "note",
}
```

### Routing map (example — fill with real policy)
```python
ROUTING = {
    "gmail":   {"vector", "sqlite"},
    "podcast": {"kg", "vector", "sqlite"},
    "article": {"kg", "vector", "sqlite"},
    "note":    {"kg", "vector"},
}
```

---

## Changes to what Codex already built

1. **Cut `export_jsonl()` / `import_jsonl()` (graph backup/restore).** Bronze is the backup. Restore = rebuild from bronze. A graph-snapshot-of-a-graph is the exact redundant complexity this rework removes.
2. **Drop the `:Document.status` (`pending`/`done`) dedup logic.** State lives in the ledger (P3). Keep only a lightweight provenance pointer: every edge carries `source_hash = content_hash` so an edge traces back to its bronze file. Tracking ingestion status inside Neo4j duplicates the ledger and will drift.
3. **Keep** the reconnect fix, the `canonical_name` backfill, the public `execute_write`, and the dead-letter idea — but note the dead-letter path is now subsumed by P10: triplets always land in `triplets.jsonl` before the KG write, so the happy path and the recovery path are the same mechanism. There is no separate "failure-only" dump.
