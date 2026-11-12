# V3 Migration Plan — Maximally Agentic Podcast Brief

A concrete, sequenced plan for taking the current V2 codebase to the V3 shape described in the design doc. Three phases (V3.0 / V3.1 / V3.2), overlapping but ordered by risk.

---

## 0. Pre-flight (1–2 days)

Things that block everything downstream. Do these first.

1. **Add a memory layer.** V3's central thesis is memory-grounded agents; today there is no memory beyond `state.db`. Build a minimal `core/memory/` with:
   - `entities` table (id, name, type, aliases, embedding)
   - `claims` table (id, claimant_entity_id, statement, episode_id, timestamp, embedding, type)
   - `sources` table (url, fetched_at, content_hash, annotations json) — doubles as fetch cache
   - `runs` table — extend the existing one with `agent`, `inputs`, `outputs`, `cost`, `duration` columns
   - `MemoryClient` with the methods called by the design doc: `search_runs`, `search_entities`, `get_claims_by_claimant`, `search_claims`, `search_related_claims`, `search_sources`
   - SQLite + `sqlite-vec` for embeddings is enough at this scale; don't reach for pgvector.
2. **Unify data models.** Replace scattered `@dataclass`es with Pydantic models in `core/models.py`. This is required input for V3.2 (Pydantic AI) and pays for itself immediately as agents pass typed objects around.
3. **Add `pytest` + a smoke test fixture** that runs one cached episode end-to-end with mocked Claude calls. Without this, agent refactors are unverifiable.
4. **Settle the open design decisions** the V3 doc lists. Concrete recommendations:
   - Pydantic AI: **wait for V3.2** (matches the doc's lean).
   - MCP transport: **stdio for now**, switch to HTTP only when Claude Desktop needs to reach in.
   - Concurrency: **per-episode asyncio** end-to-end; no job queue yet.
   - Aggregator budget: **hard cap per episode**, soft cap per claim — surfaces in the brief as "weak areas".
   - Failure mode: **degrade-not-fail throughout** (each agent has a V2-style fallback path).

---

## V3.0 — Agents in core (4–6 weeks)

Each existing service becomes a multi-step agent. Plain Python; no Pydantic AI yet. Order is by blast radius (smallest first).

### Step 1 — Scaffolding (3 days)
- `core/agents/{triage,extraction,importance,synthesis}/` with `agent.py`, `prompts.md`, `tests/`
- `core/aggregator/{router,annotator,full_mode_synthesis,lightweight}.py`
- `core/orchestrator/podcast.py` — new `process_episode` entry point; current `pipeline.run_pipeline` shrinks to a wrapper around it during the transition.
- `core/tools/` — extract crawler functions from `research/` into named tools (`semantic_scholar_search`, `arxiv_search`, `brave_search_political`, `wikipedia_search`, `google_books_search`, `pdf_read`, `transcript_segment`, `memory_search`).
- `core/config/prompts/` — move every prompt out of code. Each agent loads from disk.

### Step 2 — Triage agent (1 week)
Highest leverage, smallest scope. Build the agent loop pattern here so the others copy it.

- Input: episode metadata; lazy transcript head.
- Tools: `memory.search_runs`, `memory.search_entities`, `memory.get_claims_by_claimant`, `memory.search_claims`, `transcript_head`.
- Loop: max 3 iterations, $0.05 ceiling.
- Output: `TriageDecision` Pydantic model.
- **Acceptance:** on a hand-labelled set of 30 episodes, beats the V2 "always process" baseline by ≥ 40% skip rate at < 5% false-skip.

### Step 3 — Importance scorer (3 days)
Cheap, single-call (+ one optional tool call). Mostly an excuse to wire `memory.search_claims` end-to-end.

- Output: `ImportanceScore` per claim with `research_depth: "lightweight" | "full"`.

### Step 4 — Aggregator subsystem (2 weeks) — the real work
This is the hardest piece; do it before synthesis so synthesis has something good to call into.

1. **Crawlers as tools.** Wrap each existing API in `research/{academic,news,books}.py` as a function the router can invoke. Add `pdf_read` and `wikipedia_search`.
2. **Source cache.** Every crawler hits `memory.search_sources` first; misses write back. This alone delivers the doc's 3-month cost reduction.
3. **Router agent (`core/aggregator/router.py`).** Plan → execute → evaluate → replan loop. The "invent search proxies" prompt is the most consequential prompt in V3 — version it from day one.
4. **`evaluate_results` sub-agent.** Sonnet, scores `{quality, gaps, extra_queries}`. Used in both modes.
5. **Annotator sub-agent (`annotator.py`).** Sonnet, tags each source with relevance/credibility/position/excerpt.
6. **Full-mode synthesiser (`full_mode_synthesis.py`).** Opus, compresses 10–20 sources into a structured essay per claim. Output stored in memory.
7. **Lightweight mode (`lightweight.py`).** Keep V2's hardcoded source mix, but add the `evaluate_results` 1-shot and one replan.
8. **Public surface:** `aggregator.research(target, mode, budget_ceiling, context)` is the only entry point.

**Acceptance:** on a 20-claim test set, full-mode router produces strictly more relevant top-5 sources than V2's hardcoded mix in ≥ 70% of claims (blinded grading).

### Step 5 — Extraction agent (1 week)
Four passes, each a separate Claude call:

1. Structural — segment transcript into thematic blocks.
2. Claims — extract testable claims per block.
3. Entity resolution — query memory, assign or create entity ids.
4. Contradiction sweep — `get_claims_by_claimant` for each claimant; flag conflicts.

Fallback: if any pass times out / errors, degrade to V2 single-pass extraction and mark the result `extraction_confidence < 0.5`.

### Step 6 — Synthesis agent (1 week)
Multi-pass: draft → critique → escalate → revise. The escalation step calls back into `aggregator.research(depth="targeted")` for sections the critic flagged. **This is the biggest qualitative jump in V3** — get the rubric right.

- Treat `core/config/prompts/synthesis_critique.md` as a first-class artefact; it lives in git, has its own changelog, and gets graded against blinded brief comparisons.

### Step 7 — Orchestrator wiring + cutover (3 days)
- `core/orchestrator/podcast.py` becomes the real entry point.
- `core/pipeline.py` deletes its inline logic and just calls the orchestrator.
- Add per-episode budget tracking and the daily ceiling from `core/config/budgets.yaml`.

### V3.0 acceptance gates
- All five agents running end-to-end on 10 cached episodes.
- Aggregator router beats V2 hardcoded mix on the 20-claim test set.
- Synthesis grades higher than V2 on a blinded comparison of 10 episodes.
- Average cost per episode under $20; daily budget cap demonstrably prevents overrun.

---

## V3.1 — MCP exposure (1–2 weeks)

Start this in parallel with V3.0 once triage is stable. Wrap each agent as an MCP server.

1. **Per-agent `server.py`** under `core/agents/<name>/server.py`. Each exposes 1–3 tools — keep the surface tiny.
2. **`core/mcp/run.py`** spins up all servers (stdio subprocesses, supervised by one parent process).
3. **Transport switch.** Orchestrator gains a flag: invoke agents via Python imports (default, fast) or via MCP (verifies the contract). CI runs both; production uses imports.
4. **External-client smoke test.** Connect Claude Desktop to one agent (start with `memory.search_claims`); verify a real query works end-to-end.

V3.1 done = every agent is dual-callable and one external client demo works.

---

## V3.2 — Pydantic AI migration (2–3 weeks)

Pure refactor. One agent at a time, in this order (low risk → high):

1. Triage
2. Importance scorer
3. Synthesis
4. Extraction
5. Aggregator router

For each: replace the hand-rolled tool loop with `pydantic_ai.Agent`, declare `deps_type` and `output_type`, register tools with `@agent.tool`. The Pydantic models you wrote in pre-flight already define the shapes.

V3.2 done = no hand-rolled tool loops remain; tool I/O is fully validated; structure across `core/agents/` is uniform.

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Aggregator router prompts underperform V2's hardcoded mix at first | Keep lightweight mode hardcoded; gate full-mode behind importance ≥ 4 until router is proven |
| Cost runaway during V3.0 development | Hard daily cap from day one; per-agent cost ceilings logged to `runs` table |
| Memory layer becomes a bottleneck for synthesis (many small queries) | Batch memory reads at start of each agent loop; cache within a single `process_episode` call |
| Self-critique rubric is the new single point of failure for brief quality | Version-control the rubric; run blinded A/B against V2 weekly during rollout |
| Pydantic AI lock-in | Plain-Python V3.0 first means the migration is a refactor, not a rewrite — escape hatch preserved |

---

## Suggested first PR

Smallest useful slice that proves the V3 shape:

1. Pre-flight steps 1–3 (memory layer, Pydantic models, pytest smoke test).
2. Triage agent end-to-end (Step 2 above).
3. Orchestrator stub that calls triage and falls through to existing V2 pipeline for everything else.

This is ~1 week of work, ships value immediately (better skip decisions), and de-risks every later step.
