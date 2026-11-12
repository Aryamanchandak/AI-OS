# Research MCP — Full Implementation Plan (All Phases)

**Status as of Phase 1.1:** 33/33 tests passing. Source clients, dedup, DB persistence, trusted_sources all verified.
**Next:** Phase 1.2 — two-axis triage + expansion (requires `ANTHROPIC_API_KEY`).

---

## Quickstart for a new chat

```bash
cd "Research_MCP"
# Drop trusted_sources.yaml into the root (see §6 of the spec for structure)
# Set ANTHROPIC_API_KEY (and optionally BRAVE_API_KEY, GOOGLE_BOOKS_API_KEY)
.venv/bin/python -m pip install -e ".[dev]"   # if not already installed
.venv/bin/pytest                               # should be 22/22 green
```

---

## What already exists (Phase 1.0 complete)

### Directory layout

```
Research_MCP/
├── pyproject.toml                          # mcp, anthropic, pydantic>=2, httpx, aiosqlite, pyyaml, tenacity
├── conftest.py                             # adds src/ to sys.path (handles spaces in path)
├── .env.example                            # documents ANTHROPIC_API_KEY, BRAVE_API_KEY, GOOGLE_BOOKS_API_KEY
├── trusted_sources.yaml                    # USER-PROVIDED — drop in root before Phase 1.1
├── prompts/
│   ├── triage.md                           # v1.1 — two-axis schema + 4 calibration examples
│   ├── expansion.md                        # v1.0 — exposition vs refutation decomposition
│   ├── annotation.md                       # v1.0 — per-source structured annotation
│   ├── synthesis_exposition.md             # v1.1 — [Sn] citation rules enforced
│   └── synthesis_refutation.md             # v1.1 — [Sn] citation rules enforced
├── src/research_mcp/
│   ├── contracts.py          # ALL Pydantic models — FROZEN
│   ├── pricing.py            # dated pricing table + compute_cost()
│   ├── meter.py              # MeteredClient — JSONL + SQLite dual logging
│   ├── database.py           # SQLite schema + all helpers
│   ├── dedup.py              # fingerprinting + LogicalSource merging
│   ├── citation_gate.py      # deterministic citation verifier (no LLM)
│   ├── triage.py             # two-axis Sonnet triage + claim splitter
│   ├── expansion.py          # Opus expansion (deep only)
│   ├── annotation.py         # Sonnet per-LogicalSource annotation
│   ├── synthesis.py          # dual-mode Opus synthesis + atomic essay write
│   ├── engine.py             # full pipeline: research_topic + verify_claims
│   ├── trusted_sources.py    # load/query trusted_sources.yaml
│   ├── server.py             # FastMCP stdio server — 9 tools registered
│   └── sources/
│       ├── base.py           # SourceClient ABC + SourceUnavailableError
│       ├── semantic_scholar.py
│       ├── arxiv.py
│       ├── wikipedia.py
│       ├── brave.py          # requires BRAVE_API_KEY
│       └── google_books.py   # requires GOOGLE_BOOKS_API_KEY
├── runs/                     # on-disk per-run dirs (essays written here)
├── audit/                    # JSONL audit logs (YYYY-MM-DD.jsonl)
├── data/
│   └── research.db           # SQLite (auto-created on first run)
└── tests/
    ├── test_contracts.py
    ├── test_dedup.py
    ├── test_citation_gate.py
    └── test_pricing.py
```

---

## Architecture overview

**One adaptive pipeline. Two entry points.**

```
INPUT
  │
  ▼
TRIAGE  (Sonnet, always, every item) → {correctness, effort, confidence}
  │
  ├─ effort=silent (true+trivial) ──► SILENT LOG  (logged, not surfaced)
  │
  ├─ effort=light  (false+trivial) ──► fetch ≥1 source
  │                                    → SYNTHESIS-correction (Sonnet)
  │                                    → CITATION GATE → SURFACE
  │
  └─ effort=deep   (sophisticated / low-confidence / topic)
                    ──► EXPANSION (Opus) → proxy search queries per facet
                        → FETCH (5 source clients)
                        → DEDUP → LogicalSources
                        → ANNOTATE (Sonnet, per source)
                        → SYNTHESIS (Opus, single call):
                             correctness=false → refutation prompt
                             topic/true+rich   → exposition prompt
                        → CITATION GATE → SURFACE → write essay
```

**Two entry points:**
- `research_topic` — always deep, always exposition. Floor = deep.
- `verify_claims` — full range. Triage per claim. Most are silent/light; sophisticated claims hit deep+refutation.

**Model tiering:**

| Stage | Model | When |
|---|---|---|
| Triage, annotation, claim_split | claude-sonnet-4-6 | Always |
| Expansion | claude-opus-4-7 | deep only |
| Synthesis | claude-opus-4-7 | deep; Sonnet for light corrections |

---

## Data contracts (frozen — do not change without updating all stages)

All in `src/research_mcp/contracts.py`:

| Model | Key fields |
|---|---|
| `Provenance` | query, source_tier, fetched_via |
| `SourceRecord` | source, external_id, title, authors, published, url, raw_excerpt, content_hash, fetched_at, provenance |
| `LogicalSource` | id, fingerprint, external_ids (dict), title, authors, published, url, raw_excerpt, provenance (list) |
| `TriageResult` | correctness (true/false/topic), effort (silent/light/deep), confidence (0–1), rationale |
| `Annotation` | logical_source_id, relevance, key_findings, credibility_tier |
| `ModelCallRecord` | timestamp, model, stage, tokens_in, tokens_out, cost_usd, run_id, status |
| `RunRecord` | run_id, mode (research/verify), input, status, created_at, finished_at, cost_usd, model_calls |
| `ResearchResult` | run_id, essay_path, logical_sources, cost_usd |
| `ClaimVerdict` | claim_text, verdict (supported/contradicted/mixed/insufficient), confidence, run_id |
| `SurfacedItem` | claim_text, triage, essay_path, logical_sources |
| `BriefReview` | surfaced (list[SurfacedItem]), passed_count, run_id |

---

## MCP tools (all 9 registered in server.py)

**Engine tools:**
- `research_topic(topic, profile?, trusted_sources_only?)` → runs full deep pipeline, returns ResearchResult JSON
- `get_run_status(run_id)` → status + cost_usd
- `get_run_result(run_id)` → essay text + sources count + cost
- `verify_claims(brief, trusted_sources_only?)` → BriefReview JSON

**Source tools (direct access):**
- `search_semantic_scholar(query, profile?)`
- `search_arxiv(query, category?)`
- `search_brave(query, trusted_sources_only?)` — requires BRAVE_API_KEY
- `search_wikipedia(query)`
- `search_google_books(query)` — requires GOOGLE_BOOKS_API_KEY

---

## Phase 1.1 — Source Clients + Storage + Dedup

**Goal:** Real query fetches + persists deduped logical sources from all available sources; re-run idempotent; known duplicate collapses to one LogicalSource.

### What's already written (just needs real API calls)
All source clients are implemented. `dedup.py` is implemented. `database.py` has the full schema.

### Exit criteria (run these manually)
```python
# 1. Search from a Python script or MCP call
import asyncio, sys
sys.path.insert(0, 'src')
from research_mcp.sources.semantic_scholar import SemanticScholarClient
from research_mcp.sources.arxiv import ArXivClient
from research_mcp.dedup import merge_into_logical_sources

async def test():
    ss = SemanticScholarClient()
    ax = ArXivClient()
    ss_results = await ss.search("neuromorphic computing", limit=5)
    ax_results = await ax.search("neuromorphic computing spiking neural networks", limit=5)
    all_records = ss_results + ax_results
    sources = merge_into_logical_sources(all_records)
    print(f"Raw records: {len(all_records)}, Logical sources after dedup: {len(sources)}")
    for s in sources:
        if len(s.external_ids) > 1:
            print(f"  Collapsed duplicate: {s.title} → {s.external_ids}")

asyncio.run(test())
```

**Must verify:**
1. At least one paper appears in both SS and arXiv and collapses to one LogicalSource
2. Re-running the same query → same LogicalSource IDs in DB (no new rows)
3. `trusted_sources.yaml` loads without error: `from research_mcp.trusted_sources import load_trusted_sources; ts = load_trusted_sources(); print(ts.get_domains('finance'))`

### Key implementation notes
- `dedup.py:merge_into_logical_sources` groups by `content_fingerprint(title, first_author, year)` — same paper from different sources gets one LogicalSource with both IDs in `external_ids`
- `database.py:upsert_logical_source` uses `ON CONFLICT(fingerprint) DO UPDATE` — safe to call repeatedly
- `database.py:get_existing_fingerprints` should be called BEFORE any API search to avoid re-fetching known papers
- Brave + Google Books clients raise `SourceUnavailableError` (not crash) when keys are missing — engine handles this gracefully in `engine.py:_fetch_all`

---

## Phase 1.2 — Two-Axis Triage + Expansion

**Goal:** Three specific test cases must pass.

### What's already written
`triage.py`, `expansion.py` are fully implemented. Triage prompt (`prompts/triage.md`) includes calibration examples.

### Exit criteria (all three must hold)

```python
import asyncio, sys, os
sys.path.insert(0, 'src')
from research_mcp.database import init_db
from research_mcp.meter import MeteredClient
from research_mcp.triage import triage_item
from research_mcp.expansion import expand_topic

DB = "data/research.db"
RUN_ID = "test-triage-001"

async def test_triage():
    await init_db(DB)
    meter = MeteredClient(db_path=DB)

    # Must be false + light
    t1 = await triage_item("wind turbines are giant fans", meter, RUN_ID)
    assert t1.correctness == "false" and t1.effort == "light", f"FAIL: {t1}"
    print(f"PASS wind turbines: {t1.correctness}/{t1.effort}")

    # Must be topic + deep
    t2 = await triage_item("neuromorphic engineering", meter, RUN_ID)
    assert t2.correctness == "topic" and t2.effort == "deep", f"FAIL: {t2}"
    queries = await expand_topic("neuromorphic engineering", t2, meter, RUN_ID)
    assert len(queries) >= 3, f"Need >=3 queries, got {len(queries)}"
    print(f"PASS neuromorphic: {t2.correctness}/{t2.effort}, {len(queries)} queries")

    # Must be false + DEEP (not light) — the critical one
    t3 = await triage_item(
        "The Jevons paradox makes AI-efficiency regulation pointless", meter, RUN_ID
    )
    assert t3.correctness == "false" and t3.effort == "deep", f"FAIL: {t3}"
    print(f"PASS Jevons: {t3.correctness}/{t3.effort}")

asyncio.run(test_triage())
```

### Key implementation notes
- Confidence-driven escalation is in `triage.py:triage_item` — if `confidence < 0.7` and `effort == "light"`, effort is upgraded to `"deep"`
- If the Jevons claim comes back as `false+light` it means the model is overconfident — lower the `_CONFIDENCE_ESCALATION_THRESHOLD` in `triage.py` from 0.7 to 0.8 and retest
- Triage uses temperature=0.2 for label stability; expansion uses 0.3

---

## Phase 1.3 — Annotation + Synthesis + Citation Gate + research_topic E2E

**Goal:** A real topic produces a citation-anchored essay that passes the citation gate; cost is recorded.

### What's already written
`annotation.py`, `synthesis.py`, `citation_gate.py`, `engine.py:run_research_topic` are all implemented.

### Exit criteria

```bash
# Run via MCP or directly:
ANTHROPIC_API_KEY=sk-ant-... .venv/bin/python -c "
import asyncio, sys
sys.path.insert(0, 'src')
from research_mcp.database import init_db
from research_mcp.meter import MeteredClient
from research_mcp.engine import run_research_topic
from research_mcp.sources.semantic_scholar import SemanticScholarClient
from research_mcp.sources.arxiv import ArXivClient
from research_mcp.sources.wikipedia import WikipediaClient

async def main():
    await init_db('data/research.db')
    clients = [SemanticScholarClient(), ArXivClient(), WikipediaClient()]
    meter = MeteredClient('data/research.db')
    result = await run_research_topic(
        topic='neuromorphic engineering',
        profile=None, trusted_only=None,
        clients=clients, meter=meter, db_path='data/research.db'
    )
    print('run_id:', result.run_id)
    print('essay_path:', result.essay_path)
    print('sources:', len(result.logical_sources))
    print('cost_usd:', result.cost_usd)

asyncio.run(main())
"
```

**Must verify:**
1. Essay file exists at `runs/{run_id}/essay.md`
2. Essay contains `[S1]`, `[S2]` etc. citation tags
3. `citation_gate.verify_citations(essay_text, sources).passed == True`
4. `cost_usd > 0` in RunRecord
5. JSONL entries in `audit/YYYY-MM-DD.jsonl`

**Also run on a false+sophisticated claim (refutation path):**
```python
result = await run_research_topic(
    topic="The Jevons paradox makes AI-efficiency regulation pointless",
    ...
)
# Essay should argue AGAINST the claim with citations
```

### Key implementation notes
- `synthesis.py` selects prompt based on `triage.correctness == "false"` → refutation prompt
- Each LogicalSource gets a stable label `S1`, `S2`... in the prompt; synthesis must use these
- `citation_gate.py:verify_citations` is deterministic and checks: (1) every `[Sn]` maps to a real source, (2) every quoted string `"..."` is a substring of that source's `raw_excerpt`
- A run cannot reach `status="complete"` if the citation gate fails — `engine.py` raises RuntimeError
- Essay is written atomically: temp file + `os.rename` (see `synthesis.py`)

### Cost measurement (§11 of spec)
After ~10 real deep runs, check:
```bash
sqlite3 data/research.db "SELECT stage, model, SUM(cost_usd), COUNT(*) FROM model_calls GROUP BY stage, model;"
```
Decision tree from spec:
- Cost fine → do nothing
- Cost hurts, quality fine → add the Sonnet-draft → Opus-critique → Sonnet-revise loop
- Quality weak → fix the prompts first

---

## Phase 1.4 — verify_claims + Surface-only Output

**Goal:** A real podcast brief returns a BriefReview surfacing ONLY false/rich items; silent items logged to DB.

### What's already written
`engine.py:run_verify_claims`, `triage.py:split_claims` are implemented. Silent log table is in the DB schema.

### Exit criteria

```python
import asyncio, sys
sys.path.insert(0, 'src')
from research_mcp.database import init_db
from research_mcp.meter import MeteredClient
from research_mcp.engine import run_verify_claims
from research_mcp.sources.semantic_scholar import SemanticScholarClient
from research_mcp.sources.arxiv import ArXivClient
from research_mcp.sources.wikipedia import WikipediaClient

BRIEF = """
Water boils at 100 degrees Celsius at sea level.
Wind turbines are giant fans that use electricity to spin.
The human brain has approximately 86 billion neurons.
The Jevons paradox proves that energy efficiency improvements always increase total energy use.
Neuromorphic chips are designed to mimic biological neural networks.
"""

async def main():
    await init_db('data/research.db')
    clients = [SemanticScholarClient(), ArXivClient(), WikipediaClient()]
    meter = MeteredClient('data/research.db')
    review = await run_verify_claims(
        brief=BRIEF, trusted_only=None,
        clients=clients, meter=meter, db_path='data/research.db'
    )
    print(f"Surfaced: {len(review.surfaced)} items")
    print(f"Passed silently: {review.passed_count}")
    for item in review.surfaced:
        print(f"  [{item.triage.correctness}/{item.triage.effort}] {item.claim_text[:60]}")

asyncio.run(main())
```

**Must verify:**
1. `review.surfaced` contains only the false/sophisticated claims (wind turbines, Jevons)
2. `review.passed_count` = number of true+trivial claims (water, neurons)
3. All surfaced items have valid citations (their essays pass the gate)
4. `sqlite3 data/research.db "SELECT claim_text, correctness FROM silent_log WHERE run_id = '...';"` shows the passed claims

### Key implementation notes
- `split_claims` uses a cheap Sonnet call to split the brief into individual claims
- Each claim is triaged independently; all triage calls fire in parallel (`asyncio.gather`)
- Silent items go to `silent_log` table only — never returned to caller
- `passed_count` is the silent count, not a quality judgment
- The podcast integration path: swap the podcast's inline research call for `run_verify_claims` via the internal Python client; the MCP server is for external callers

---

## Absorption seam (run after Phase 1.3 or 1.4)

The spec requires a dry-run move to verify the package can be absorbed into `core/aggregator/`:

```bash
# Simulate the move
cp -r "Research_MCP/src/research_mcp" "/path/to/core/aggregator/research-mcp/src/research_mcp"
# Update RESEARCH_MCP_DB_PATH and RESEARCH_MCP_TRUSTED_SOURCES_PATH env vars to point to new location
# Run: python -m research_mcp.server  — should start from new path
# Document any import/config changes needed as the "one-checklist diff for Phase 2"
```

---

## Phase 2 preview (out of scope — do not build yet)

- Connect to existing **ChromaDB** (resolve one-collection-per-project → shared/cross-collection)
- Connect to existing **NetworkX KG** (register aggregator entities)
- Light up `query_memory` / `resolve_entity` MCP tools
- Retroactively index all Phase 1 essays + silent log (clean, fully-provenanced)
- Semantic query cache (embeddings-based dedup before API calls)
- Subscription / headless-browser source clients

---

## Hard constraints (must hold across all phases)

1. **Contracts frozen** — `contracts.py` is not changed without updating every stage that uses the affected model
2. **Every LLM call through MeteredClient** — no bare `anthropic.messages.create` anywhere
3. **Prompts are files** — no inline prompt strings in Python code; always `prompts/*.md`
4. **Idempotent writes** — `INSERT OR IGNORE`; essays via temp+`os.rename`
5. **Citation gate is hard** — a run with `gate.passed=False` must not reach `status="complete"`
6. **Dedup before annotation** — `merge_into_logical_sources` runs before any annotation call
7. **No destructive ops** — archive, never delete; cache is the only ephemeral exception

---

## Useful commands

```bash
# Run all tests
.venv/bin/pytest -v

# Check metered costs
sqlite3 data/research.db "SELECT stage, model, SUM(cost_usd) as total, COUNT(*) as calls FROM model_calls GROUP BY stage, model;"

# Inspect a run
sqlite3 data/research.db "SELECT run_id, status, cost_usd FROM runs ORDER BY created_at DESC LIMIT 5;"

# Read the silent log
sqlite3 data/research.db "SELECT claim_text, correctness, confidence FROM silent_log ORDER BY timestamp DESC LIMIT 10;"

# Tail today's audit log
tail -f audit/$(python3 -c "from datetime import date; print(date.today())")*.jsonl | python3 -m json.tool

# Start the MCP server (stdio)
ANTHROPIC_API_KEY=... .venv/bin/research-mcp
```
