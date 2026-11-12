# Integration Requirements — changes needed outside study-system

**Written:** 2026-07-08 · **Revised:** 2026-07-09 — now confirmed, for handoff (e.g. to Codex) in each target repo.
**Scope:** everything here is a change to `Database/knowledge-graph`, `Database/vector-db`, `Database/sqlite`, or `llm_gateway` — none of it is study-system code. study-system's own task list is in `REDESIGN_PLAN.md`.

---

## 1. `knowledge-graph` (Neo4j) — three concrete asks

### 1.1 Fix: domain is hardcoded, not read from capture metadata
**Confirmed in code**, not a guess: `lib/ledger.py`'s `Item` class already carries a `metadata: dict` field, persisted through the ledger. But `knowledge_graph/extraction.py` (~line 163) writes every triplet with a **literal hardcoded** `"domain": "general"`, ignoring `item.metadata` even though `item` is in scope right there. Fix:
```python
# before
"domain": "general",
# after
"domain": item.metadata.get("domain", "general"),
```
Same pattern applies to both `subject_domain`/`object_domain` when `ingestion.py::write_kg` builds its rows from the JSONL (currently `data.get("domain", "general")` — this part already reads correctly from the triplet JSON, so only `extraction.py`'s write side needs the fix).
**Caller side (study-system):** will pass `capture_raw_data(source="note", content=..., metadata={"domain": "fixed_income"})` — no LLM classification needed, study-system already knows the domain of what it's capturing.

### 1.2 New read method: list concepts by domain
No existing method lists concepts — only `kg_search_concepts(query, limit)` (fuzzy name search) and single-node lookups. Add:
```python
def kg_list_concepts(domain: str) -> list[KGNode]:
    """All :Concept nodes with this domain. Full set each call — no delta/since needed."""
```
**Used for:** study-system mirrors this domain-scoped list into its own local SQLite as its "topics that exist" registry, after each ingestion run.

### 1.3 New read method: concepts by source
Add a "read by source" method:
```python
def kg_concepts_for_source(item_id: str) -> list[KGNode]:
    """All :Concept nodes with an edge whose source == item_id."""
```
**Used for:** staleness tracing (§4 below) — when a note is re-captured with changed content, find which concepts/facts were derived from the old version.

### 1.4 New deliverable: ingestion review UI (abbreviation/nickname/spelling correction)
**This was previously misscoped as a study-system "concept-identity bridge" — it is not. Correct scope:** a human-in-the-loop screen, built the same way `Page Scanner` builds its review cockpit (local FastAPI server + a static HTML/JS review page, `Page Scanner/server.py` + `static/review.js` as the reference pattern — desk-only, never phone-exposed), that sits **on top of the KG + vector-db, at ingestion time**. It shows incoming highlights/captures as they're about to become (or have just become) KG nodes/vector chunks, and lets you:
- fix spelling mistakes in extracted concept names,
- map personal shorthand to canonical names (e.g. "DUR" → "Duration", "MAC DUR" → "Macaulay Duration"),
- approve/reject before (or shortly after) the name is written into Neo4j / used as chunk metadata.

This is a real, undeferred deliverable — it belongs to the KG/vector-db/ingestion layer in `Database/`, not to study-system, since it operates on every capture regardless of which downstream project (study-system or otherwise) the note is for.

### TODO (not blocking, backlog for that repo)
- Multiple KGs / domain partitioning as the corpus grows beyond a single flat graph.
- Hidden-link discovery as a proactive feature (`kg_reachable`/`kg_neighbors` already support the traversal; the missing piece is a periodic pass that surfaces non-obvious connections without an explicit query).

---

## 2. `vector-db` (ChromaDB + Ollama)

- **No structural change required.** Metadata pass-through already confirmed working (`**item.metadata` lands on every chunk) — domain/topic-scoped retrieval works today as long as the caller passes that metadata at capture time.
- Shares the same ingestion-review-UI deliverable as §1.4 (cross-referenced, not duplicated) — abbreviation correction should presumably affect chunk metadata consistency too.

---

## 3. Shared SQLite (`Database/sqlite/`)

### 3.1 New tables for quiz/session logging (unchanged from prior spec, now confirmed)
```sql
CREATE TABLE learning_systems_sessions (
  id TEXT PRIMARY KEY, project TEXT NOT NULL DEFAULT 'study_system',
  mode TEXT NOT NULL, scope_json TEXT, started_at TEXT NOT NULL, ended_at TEXT
);
CREATE TABLE learning_systems_attempts (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES learning_systems_sessions(id),
  card_id TEXT NOT NULL, answer TEXT, correct INTEGER, answered_at TEXT NOT NULL
);
CREATE TABLE learning_systems_feedback (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, card_id TEXT,
  note TEXT NOT NULL, created_at TEXT NOT NULL
);
```

### 3.2 A home for study-system's own private data
Not a schema change — a location: create `Database/study-system/` and put study-system's own SQLite file there (e.g. `Database/study-system/study_system.db`). Confirmed: study-system's data does **not** live inside the `study-system/` code repo. study-system's own code just points its `SQLITE_PATH` config at that location.

---

## 4. `llm_gateway`

### 4.1 New usage table (unchanged from prior spec, now confirmed)
```sql
CREATE TABLE learning_systems_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, operation TEXT NOT NULL,
  provider TEXT NOT NULL, model TEXT NOT NULL,
  input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
  latency_ms INTEGER DEFAULT 0, status TEXT, error TEXT
);
```
Add an optional `consumer` param to `LLM.chat()`/`LLM.embed()` in `client.py`; when `consumer="study_system"`, the gateway server also writes to this table (in addition to its existing gateway-wide `calls` table).

---

## 5. Open problem, not yet resolved — source staleness

Not "cards go stale from disuse" (confirmed not a concern — a card that's been made and used is fine regardless of what happens to the source afterward). The real question: **when the underlying source material changes (a note gets edited, a rule/regulation changes), how does anything downstream know the facts/cards derived from the old version might now be wrong?**

Seed of a mechanism, not a full answer: bronze items are immutable and content-hashed; a re-capture of "the same" note produces a *new* item with a new hash, with no automatic link declaring it supersedes the old one. §1.3's `kg_concepts_for_source(item_id)` lets you trace forward from a known old source to affected concepts, but nothing currently detects "this new capture supersedes that old one" in the first place. Needs more thought before it's a real task — flagged here so it isn't lost, not scoped yet.

---

## Summary — what's now a confirmed ask per target

| Target | Confirmed asks |
|---|---|
| `knowledge-graph` | domain-from-metadata fix (§1.1), `kg_list_concepts` (§1.2), `kg_concepts_for_source` (§1.3), ingestion review UI (§1.4) |
| `vector-db` | none required; shares §1.4 |
| Shared SQLite | 3 new tables (§3.1), new home for study-system's own DB (§3.2) |
| `llm_gateway` | 1 new table + `consumer` param (§4.1) |
| study-system | see `REDESIGN_PLAN.md` |
