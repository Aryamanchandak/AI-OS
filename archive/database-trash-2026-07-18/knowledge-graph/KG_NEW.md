# Codex Plan — Knowledge Graph Slice (Storage Rework Test Case)

> **Historical (2026-07-05).** This was the build plan for the KG slice; it has been
> **implemented**. For how the shipped system actually works, read the top-level
> `../WORKFLOW.md` (accurate end-to-end trace) and this folder's `CLAUDE.md`. Kept for
> rationale/history — not a description of current code.

**Read `../../Constitution/STORAGE_PRINCIPLES.md` first.** This plan implements that architecture for **one consumer only — the knowledge graph** — as the proving ground before vector and SQLite get the same treatment.

**Scope discipline:** build the minimal shared core (bronze + ledger), rewire KG to consume from it, get one item flowing capture → bronze → button → triplets → Neo4j with a heartbeat. Synchronous extraction (no Batch API yet). No vector, no SQLite, no spellcheck, no MCP wrapper. Those are named in "Deferred" and must not creep in.

**Before writing anything:** open the current `knowledge_graph/` files and confirm the actual names, signatures, and line numbers. The symbols below come from prior session notes, not a live read — treat them as the *target shape*, map them to what's really there, and flag any mismatch instead of guessing.

---

## 0. Reconcile with what already exists

Codex previously implemented several changes. This rework keeps some, cuts some, modifies some. Do this reconciliation **first** so you're not building on top of code that's about to be deleted.

### KEEP (unchanged)
- Reconnect fix in `KGStore._get_driver()` (no longer sticky-disabled after one failure).
- `canonical_name` backfill in `upsert_edge_batch()` / `upsert_edge()` (`coalesce(subject_name, subject_id)` on CREATE).
- Public `KGStore.execute_write(cypher, rows)`.
- `KGEdge` carrying subject/object names and domains.

### CUT (delete)
- `KGStore.export_jsonl()` and `KGStore.import_jsonl()`. Bronze is the backup; a graph-snapshot-of-a-graph is the redundancy this rework removes. (The UNWIND-rows write logic inside `import_jsonl` is useful — fold it into `write_kg()` below, then delete the method.)
- The `:Document` MERGE with `status` pending/done dedup in `ingestion.py`, and any `document_id_unique` constraint added for it. Ingestion state lives in the ledger now (P3), not in Neo4j.
- `KGIngester.replay_failed()` and the failure-only dead-letter JSONL write. Superseded: triplets are now **always** persisted before the KG write, so the happy path and recovery path are the same code (P10).

### MODIFY
- `KGEdge`: rename the `doc_id` field to `source_hash` (the bronze content hash — the provenance pointer that replaces `:Document`).
- `KGIngester.ingest(IngestDocument)` (real-time, extract+write in one call): split into two independently callable steps — `extract_triplets()` and `write_kg()` — and remove the combined real-time entry point.

---

## 1. `storage_core` — minimal shared foundation

New package, **sibling** to `knowledge-graph/` (not inside it), so vector/SQLite can depend on it later without importing through the KG. One-way dependency: consumers → core, never reverse.

```
Database/
  storage_core/
    pyproject.toml                 # requires-python >=3.11; deps: pydantic>=2
    src/storage_core/
      __init__.py                  # exports: capture, init_ledger, pending, mark, Item, ...
      ledger.sql                   # DDL (below)
      ids.py
      paths.py
      ledger.py
      capture.py
      heartbeat.py
      config.py                    # SOURCE_REGISTRY, ROUTING, STORAGE_ROOT resolution
  knowledge-graph/                 # existing, modified in §2
  storage_data/                    # NEW, gitignored — the on-disk root (STORAGE_ROOT)
    bronze/
    _ledger.sqlite
```

Install editable into the **same `.venv`** already created: `.venv/bin/pip install -e ../storage_core`.

### 1.1 `config.py`
```python
import os
from pathlib import Path

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "")).expanduser()  # required; raise if unset

SOURCE_REGISTRY = {        # code -> full name. Fixed list, edit rarely. Fill real values.
    "nt": "note",
    "pc": "podcast",
    "ar": "article",
}

ROUTING = {                # source -> set of targets. Fill real policy.
    "note":    {"kg"},     # KG slice only for now
    "podcast": {"kg"},
    "article": {"kg"},
}
```
The data root is the old "core truth source folder," renamed: on disk it's `STORAGE_ROOT/bronze/`, ledger at `STORAGE_ROOT/_ledger.sqlite`.

### 1.2 `ledger.sql`
```sql
CREATE TABLE IF NOT EXISTS items (
    content_hash  TEXT PRIMARY KEY,
    item_id       TEXT NOT NULL,
    source        TEXT NOT NULL,
    captured_at   TEXT NOT NULL,
    bronze_path   TEXT NOT NULL,        -- relative to STORAGE_ROOT
    authored      INTEGER NOT NULL DEFAULT 0,
    metadata      TEXT
);
CREATE TABLE IF NOT EXISTS processing (
    content_hash  TEXT NOT NULL REFERENCES items(content_hash),
    target        TEXT NOT NULL,        -- 'kg'
    stage         TEXT NOT NULL,        -- 'extracted' | 'written'
    status        TEXT NOT NULL,        -- 'pending' | 'done' | 'failed'
    artifact_path TEXT,
    attempted_at  TEXT,
    error         TEXT,
    PRIMARY KEY (content_hash, target, stage)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    target        TEXT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    items_seen    INTEGER DEFAULT 0,
    items_done    INTEGER DEFAULT 0,
    items_failed  INTEGER DEFAULT 0,
    status        TEXT
);
CREATE INDEX IF NOT EXISTS idx_proc_lookup ON processing(target, stage, status);
```

### 1.3 `ids.py`
```python
def normalize(body: str) -> str          # strip trailing ws per line, normalize newlines; used ONLY for hashing
def content_hash(body: str) -> str       # sha256(normalize(body)).hexdigest()
def code_for(source: str) -> str         # reverse lookup in SOURCE_REGISTRY; raise on unknown
def mint_item_id(source: str) -> str     # f"{code_for(source)}_{rand4}", rand4 in [a-z0-9]{4}
```

### 1.4 `paths.py`
```python
from datetime import datetime, timezone

def today() -> str                       # UTC date, "YYYY-MM-DD"
def bronze_dir(source: str) -> Path      # STORAGE_ROOT/bronze/{today}/{source}/bronze
def triplets_dir(source: str, date: str) -> Path  # .../{date}/{source}/triplets
def abs_path(rel: str) -> Path           # STORAGE_ROOT / rel
```

### 1.5 `ledger.py`
```python
@dataclass
class Item:
    content_hash: str; item_id: str; source: str; captured_at: str
    bronze_path: str; authored: bool; metadata: dict
    def bronze_abs(self) -> Path
    def triplets_abs(self) -> Path       # derives triplets path from bronze_path + item_id

def init_ledger() -> None                # executescript(ledger.sql)
def register_item(item: Item) -> bool    # INSERT; return False if content_hash exists (dup)
def get_item(content_hash: str) -> Item | None
def is_done(content_hash, target, stage) -> bool
def mark(content_hash, target, stage, status, artifact_path=None, error=None) -> None
def pending(target: str, stage: str) -> list[Item]:
    """Items whose ROUTING[source] contains target AND have no
       processing row (target, stage, status='done'). Ledger query only."""
```

### 1.6 `capture.py`
```python
class CaptureResult(BaseModel):
    duplicate: bool; content_hash: str; item_id: str; path: str | None = None

def capture(source, content, metadata=None, authored=False) -> CaptureResult:
    """
    h = content_hash(content)
    if get_item(h): return CaptureResult(duplicate=True, content_hash=h, item_id=<existing>)
    item_id = mint_item_id(source)
    d = bronze_dir(source); d.mkdir(parents=True, exist_ok=True)
    f = d / f"{item_id}.md"
    write YAML frontmatter (item_id, source, content_hash=h, captured_at, authored, **metadata) + "\n" + content
    os.chmod(f, 0o444)                    # immutability enforced at the file
    register_item(Item(... bronze_path=f.relative_to(STORAGE_ROOT) ...))
    return CaptureResult(duplicate=False, content_hash=h, item_id=item_id, path=str(f))
    """
```
For the test, `capture()` is called directly. The MCP wrapper around it is a thin deferred layer (Deferred §5).

### 1.7 `heartbeat.py`
```python
def record_run_start(target) -> int
def record_run_end(run_id, seen, done, failed, status) -> None
def check_staleness(max_age_days: int = 3) -> None:
    """Find items routed to any target without (target,'written','done').
       If the oldest such item's captured_at is older than max_age_days,
       fire: osascript -e 'display notification "<n> items uningested for <d>d" with title "Storage"'.
       Button-triggered model: staleness = unprocessed bronze age, NOT cron timing."""
```

---

## 2. `knowledge_graph/` changes

### 2.1 `models.py`
- `KGEdge`: keep name/domain fields; rename `doc_id` → `source_hash`.

### 2.2 Split `KGIngester.ingest()` into two methods
`ingestion.py`. Both take an `Item` (from `storage_core`). KG now depends on `storage_core`.

```python
def extract_triplets(self, item: Item) -> str:
    """
    Read item.bronze_abs() — the BRONZE file, never a cleaned copy (P1).
    Strip frontmatter, pass body to Claude (existing extraction prompt/logic).
    Idempotent: if item.triplets_abs() exists AND is_done(hash,'kg','extracted'),
        return its path without calling Claude.
    Write one triplet per line to triplets_abs():
        {"subject","subject_name","predicate","object","object_name","domain","source_hash"}
        where source_hash = item.content_hash.
    Success -> mark(hash,'kg','extracted','done', artifact_path).
    Failure -> mark(hash,'kg','extracted','failed', error=...); raise.
    """

def write_kg(self, item: Item, triplets_path: str) -> None:
    """
    Read jsonl. UNWIND rows -> MERGE (a)-[:KG_EDGE]->(b) via store.execute_write
        (reuse the deleted import_jsonl Cypher).
    Each edge: SET r.source_hash = row.source_hash (provenance, replaces :Document).
    Backfill canonical_name = coalesce(subject_name, subject) on CREATE.
    Idempotent MERGE — safe to repeat.
    Success -> mark(hash,'kg','written','done'). Failure -> mark(...,'failed', error); raise.
    """
```
Delete the old combined `ingest()` entry point, `replay_failed()`, and the `:Document`/dead-letter code (per §0).

### 2.3 Orchestrator `knowledge_graph/run.py`
The single entry point the button calls.
```python
def run_kg() -> None:
    init_ledger()
    rid = record_run_start("kg")
    store = KGStore(); ing = KGIngester(store)
    seen = done = failed = 0
    for item in pending("kg", "written"):
        seen += 1
        try:
            tp = item.triplets_abs() if is_done(item.content_hash,"kg","extracted") \
                 else ing.extract_triplets(item)
            ing.write_kg(item, str(tp))
            done += 1
        except Exception as e:
            failed += 1; log.exception(e)   # step already marked failed
    record_run_end(rid, seen, done, failed, "ok" if not failed else "error")
    store.close()
    check_staleness()

if __name__ == "__main__":
    run_kg()
```

### 2.4 Automator button
"Run Shell Script" action:
```bash
cd /Users/aryamanchandak/Documents/AI\ Code/Database/knowledge-graph
STORAGE_ROOT=/Users/aryamanchandak/Documents/AI\ Code/Database/storage_data \
NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=... \
ANTHROPIC_API_KEY=sk-... \
.venv/bin/python -m knowledge_graph.run
```

---

## 3. Verification

### 3.1 Static (Codex can run in-sandbox, no Neo4j needed)
```bash
.venv/bin/pip install -e ../storage_core
.venv/bin/python -m compileall ../storage_core/src knowledge-graph/src   # clean
.venv/bin/python -c "import storage_core, knowledge_graph"               # imports ok
.venv/bin/python -c "from storage_core import init_ledger; import os; \
  os.environ['STORAGE_ROOT']='/tmp/sd'; init_ledger(); print('ledger ok')"
# capture + dedup (no Neo4j):
.venv/bin/python -c "
import os; os.environ['STORAGE_ROOT']='/tmp/sd'
from storage_core import init_ledger, capture
init_ledger()
print(capture('note','Interest rates affect bond prices inversely. Duration measures bond price sensitivity.', authored=True))
print(capture('note','Interest rates affect bond prices inversely. Duration measures bond price sensitivity.', authored=True))  # duplicate=True
"
```
Confirm: a `0444` file under `/tmp/sd/bronze/<date>/note/bronze/`, one `items` row, second capture returns `duplicate=True` and writes nothing.

### 3.2 Full slice (on the Mac, Neo4j running)
```python
import os; os.environ["STORAGE_ROOT"] = ".../Database/storage_data"
from storage_core import init_ledger, capture
from knowledge_graph.run import run_kg
from knowledge_graph import KGStore

init_ledger()
capture("note", "Interest rates affect bond prices inversely. Duration measures bond price sensitivity.", authored=True)
run_kg()

store = KGStore()
print(store.neighbors("interest_rates", direction="outgoing"))   # [GraphHit(id='bond_prices', name='...', ...)]
store.close()
```
Confirm: `triplets/<id>.jsonl` exists; edges in Neo4j each have `source_hash`; ledger shows `(kg,extracted,done)` and `(kg,written,done)`.

### 3.3 The property that matters most — recovery == happy path
```python
# 1. Stop Neo4j. run_kg() -> extraction succeeds (jsonl written), write fails:
#    ledger (kg,extracted,done), (kg,written,failed) with error. ZERO further Claude cost on retry.
# 2. Start Neo4j. run_kg() -> write succeeds from existing jsonl, NO re-extraction (no Claude call).
# 3. run_kg() again with nothing new -> zero Claude calls, zero duplicate edges (idempotent MERGE).
```
If step 2 re-calls Claude, the extracted-stage idempotency guard is wrong — fix before moving on.

---

## 4. Acceptance criteria
- [ ] `storage_core` installs editable into the existing `.venv`; both packages import; `compileall` clean.
- [ ] `capture()` writes a read-only bronze md with frontmatter; identical content is deduped by `content_hash`.
- [ ] One captured note flows through `run_kg()` to Neo4j; edges carry `source_hash`; ledger reflects both stages done.
- [ ] Neo4j-down → triplets persist, write marked failed, retry costs no Claude tokens; Neo4j-up → write completes from jsonl with no re-extraction.
- [ ] Re-run with no new items = no Claude calls, no duplicate edges.
- [ ] `export_jsonl`/`import_jsonl`, `:Document` status, `replay_failed`, and the combined real-time `ingest()` are gone; `git grep` finds no references.
- [ ] `check_staleness(max_age_days=0)` fires a macOS notification.

---

## 5. Deferred — must not appear in this slice
- **Batch API.** Synchronous Claude extraction proves the path; swap to the Anthropic Batch API only after §4 passes (it adds in-flight `pending` state to the extracted stage — don't entangle that with first validation).
- **Vector + SQLite consumers.** Same core, same orchestrator shape, later. Expect SQLite's own schema to be reworked to align — out of scope here.
- **MCP wrapper** around `capture()` — thin layer, add once the pipeline is trusted.
- **Spellcheck** — off the provenance path entirely (P1/P2); authored-only, certain-corrections-only, whenever.
- **Rebuild-from-bronze script** — the deletion of `export/import_jsonl` is safe because this will replace it: nuke Neo4j, replay every `triplets/*.jsonl` through `write_kg` with zero Claude spend. Build it in the backup pass, not now.
- **`:Document` nodes** as pure provenance anchors — only if querying by `source_hash` proves insufficient. Never with status fields.
