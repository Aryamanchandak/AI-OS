# Combining podcast-brief + Research_MCP + the KG/Vec-DB Study System

*An honest analysis of three repos that were designed to be one system — and how to actually combine them.*

**Author:** analysis pass, 2026-06-10
**Scope:** `Podcast to Text /podcast-brief`, `Research_MCP`, `KG + Vec DB + study system`
**Tone:** no sugar-coating. Fault lines and unbuilt work are stated plainly.

---

## 1. The headline finding

**Research_MCP was authored as podcast-brief's V3 "aggregator."** This is not a coincidence I'm
inferring from surface similarity — it is written into the specs of both projects:

- **`Research MCP — Phase 1 Build Plan (v3).md` §4** ("Locked decisions"):
  *"standalone repo, absorbable into `core/aggregator/`."*
- **Phase 1.4 exit criterion** (same doc): *"podcast swaps its inline research path for the internal
  Python client."*
- **`podcast-brief/V3_PLAN.md` Step 4** — *"Aggregator subsystem (2 weeks) — the real work"* — lists
  exactly the components Research_MCP already built: a router (plan→execute→evaluate→replan), an
  `evaluate_results` sub-agent, an annotator, a full-mode synthesiser, a source cache, and a single
  public `research()` surface.
- **Code-level proof.** Both projects implement `search_semantic_scholar` against the identical
  endpoint `https://api.semanticscholar.org/graph/v1/paper/search` with the same field set.
  `podcast-brief/research/academic.py:53` is the synchronous, `@dataclass`-based V2.
  `Research_MCP/src/research_mcp/sources/semantic_scholar.py:44` is the async, Pydantic-typed,
  retry-backed, deduped, metered, citation-gated V3 of *the same function*.

And both roadmaps independently name the **same memory backend**. Research_MCP's Phase 2 preview says
*"connect to existing ChromaDB + NetworkX KG."* The study system **is** that backend:
`store/vector_store.py` is a ChromaDB wrapper and `store/kg_store.py` is a NetworkX `DiGraph` over
SQLite.

> **So this is not three projects that *could* combine. It is one system that was designed across three
> repos and then only partially built.** The seam between them exists on paper. Most of the system on
> either side of that seam does not exist in code yet.

---

## 2. What each system actually is (today, not aspirationally)

| System | What it does | Real state right now |
|---|---|---|
| **podcast-brief** | podcast URL → audio → transcript (Deepgram) → typed claims → research → Opus brief → Readwise Reader | **V2.** `core/` contains only `config.py`, `pipeline.py`, `state.py`. Research is the **hardcoded profile mix** at `pipeline.py:124-159`. **None of the V3 design** (agents, aggregator, orchestrator, memory layer) is built. The fancy module tree (`extraction/`, `summarisation/`, …) is a reorg of V2, not V3. |
| **Research_MCP** | adaptive research engine: two-axis triage → Opus expansion → multi-source fetch → dedup → annotate → dual-mode synthesis → hard citation gate. Exposed as a FastMCP stdio server **and** an internal Python client. | **Phase 1 complete; tests green.** The plumbing is real and rigorous. But the **intelligence is deliberately deferred** (Build Plan §15): triage "judging well" (separating sophisticated-wrong from sophisticated-right), expansion's taste/world-model, and the semantic query cache are all explicitly *not* built. The path is shipped; the judgment is not. |
| **study system** | Obsidian vault → extract concepts/atomic-facts/KG-triplets → flashcards + MCQ → FSRS spaced-repetition review | **Phases 1–2 partial.** It owns the ChromaDB + NetworkX stores the other two roadmaps depend on — but those stores have **named holes** (§4). Phases 3–5 (director, hidden-link discovery, **planner integration**) are "Not started." |

---

## 3. The concrete overlaps (why merging is natural)

These three were clearly built by the same hand, to the same conventions:

| Concern | podcast-brief | Research_MCP | study system |
|---|---|---|---|
| **Source clients** | `research/{academic,news,books}.py` — SS, arXiv, Brave, Google Books, Wikipedia (hardcoded mix) | `sources/` — same five, each a `SourceClient` behind one interface, each an MCP tool | — |
| **`trusted_sources.yaml`** | `config/trusted_sources.yaml` (news whitelist) | `trusted_sources.yaml` (tiered, tri-state `trusted_sources_only`) | — |
| **Prompts-as-files** | profile prompts in `config/prompts/*.md` (but comparison prompt inline) | strict, versioned `prompts/*.md` | versioned `prompts/` (but unvalidated vars) |
| **Pydantic contracts** | not yet (`@dataclass`); V3 preflight plans the migration | frozen `contracts.py` | `types/{extraction,card,kg}.py` |
| **Model tiering** | Sonnet extract / Opus synthesis | Sonnet triage·annotate / Opus expand·synthesise | Sonnet extract / OpenAI gpt-4o-mini generate |
| **Cost metering** | none (bare SDK calls) | `MeteredClient` (JSONL + SQLite, dated pricing) — the rigorous one | `LLMClients` spend_log (but buggy, §4.3) |
| **Memory target** | V3 plans `core/memory/` (entities/claims/sources/runs) | Phase 2: "connect to existing ChromaDB + NetworkX KG" | **is** that ChromaDB + NetworkX KG |

The overlap is not cosmetic. It is the same architecture expressed at three different maturity levels.

---

## 4. Fault lines — where the merge is NOT clean

This is the part nobody wrote down. Combining these is not a copy-paste; here is exactly where it
fights you.

### 4.1 Two incompatible "intelligence" models, not one
podcast-brief extracts **typed claims** (`paper_reference`, `statistic`, `model_or_method`,
`prediction`) and routes research **by profile** (academic / current_events / hybrid → which source
pool). Research_MCP **deliberately throws claim_type away** ("engine infers") and routes **by
correctness × effort** (the two-axis triage). These are different control-flow philosophies. Dropping
Research_MCP in obsoletes podcast-brief's profile routing *and* part of its typed-claim extraction.
**Someone has to decide which control flow wins** — you can't run both. (Recommendation in §6: the
two-axis engine wins; profile becomes a *source-prioritisation hint*, exactly as Research_MCP's
`profile` param already intends.)

### 4.2 Three data-model worlds, zero shared identity
- podcast-brief: `@dataclass Paper`, `AcademicFinding`, … — **not even Pydantic**.
- Research_MCP: frozen Pydantic `SourceRecord`, `LogicalSource`, `TriageResult`, `ClaimVerdict`, …
- study system: `Concept`, `AtomicFact`, `Triplet`, `KGNode`, `KGEdge`, `Card`.

A "claim" in podcast-brief ≠ a `ClaimVerdict` in Research_MCP ≠ a `Concept` in study. **There is no
shared entity namespace.** An entity mentioned in a podcast cannot resolve to the same node as the
same entity in your study vault. The entire payoff of a unified memory — cross-references — is a thing
the current types **cannot even express**.

### 4.3 Three metering systems, and one logs the wrong number
- Research_MCP: `MeteredClient` → JSONL audit + SQLite `model_calls`, dated/versioned pricing. Correct.
- podcast-brief: **bare `anthropic.Anthropic()` calls inline** (`research/academic.py:175`). **No
  metering at all.**
- study system: `LLMClients.call()` logs spend, **but** its cost table has `claude-sonnet-4-5` while
  the configured model is `claude-sonnet-4-6` — so **extraction cost is logged at the wrong rate**
  (per `OVERVIEW.md` risk #8). Its `cost_ceiling_monthly_usd` is **defined but never checked** (risk
  #3) — runaway ingestion will not halt at the limit.

There is **no global budget** across the three. A combined system today could overspend silently in
two of the three components.

### 4.4 The shared memory backend is itself half-built
This is the load-bearing assumption of the whole vision, and it has holes the study system's own
`OVERVIEW.md` documents under "Known Architectural Risks":
- `retrieve_atomic_facts_for_concept` **always returns `[]`** (risk #6) — ChromaDB retrieval is
  unfinished. The vector store can store but not yet *retrieve* facts for context.
- **Cross-file KG triplets are silently dropped** (risk #1) — when subject and object live in
  different files. The graph is sparsest **exactly at cross-document links**, which are the valuable
  ones for an OS-wide knowledge graph.
- ChromaDB is **optional with graceful degradation** (the OVERVIEW says the system "works without
  it") — i.e. it was built to run *without* the very layer the other two projects want to build on.

You cannot treat this as a finished substrate. It needs work before anything depends on it.

### 4.5 Async vs sync seam
Research_MCP is fully async (`httpx`, `asyncio.gather`). podcast-brief is synchronous (`requests`,
`time.sleep(0.3)` for rate-limiting). The study system is sync **and** carries a macOS `fork()`
landmine (its `CLAUDE.md`: "No `multiprocessing` with `fork()`"). Wiring the sync podcast pipeline to
the async aggregator requires a deliberate event-loop boundary (`asyncio.run`/`run_until_complete`) —
small, but a real seam that has to be designed, not assumed.

### 4.6 Citation/grounding rigor is inconsistent
- Research_MCP: a **hard, deterministic citation gate** — every quote must be a substring of the
  cited source's stored excerpt, or the run fails. Strict.
- podcast-brief: **soft** — it avoids inventing citations ("notes 'no papers found'") but has no gate;
  synthesis can still overstate.
- study system: **probabilistic** — grounds only ~20% of generated cards.

Merging raises podcast-brief's bar (good), but the study system's cards stay weakly grounded. A
"shared truth layer" with three different standards of proof is not yet a shared truth layer.

### 4.7 Prompts-as-files only partly adopted
Research_MCP is strict and versioned. The study system uses files but **doesn't validate template
variable names** (a `{{VAR}}` mismatch silently produces a bad prompt) and its `PROMPTS_DIR` breaks on
non-editable installs. podcast-brief keeps profile prompts as files **but inlines the
comparison/extraction prompt in Python** (`research/academic.py:233`). Consolidation means picking the
strict convention and dragging the other two up to it.

### 4.8 Model management drifts three ways
Config constants (podcast-brief) vs hardcoded `opus-4-7` / `sonnet-4-6` in specs/prompts
(Research_MCP) vs mixed Anthropic + OpenAI with a wrong cost row (study). **No single source of truth**
for which model is used where, or what it costs.

---

## 5. What still needs to be built (the honest "not done" list)

- **The shared memory *service* does not exist.** It is named in *both* roadmaps and built in
  *neither*. Research_MCP Phase 2 is explicitly *"out of scope — do not build yet."* podcast-brief's
  `core/memory/` (entities / claims / sources / runs tables + a `MemoryClient` with
  `search_entities`, `search_claims`, `search_sources`, …) lives in the **plan**, not the code. The
  study system's stores exist but can't even retrieve facts yet (§4.4).
- **podcast-brief V3 is ≈0% built.** No triage agent, importance scorer, aggregator router,
  multi-pass extraction, or self-critique synthesis. The directories `core/{agents,aggregator,
  orchestrator,tools}/` from the V3 plan **do not exist**.
- **Research_MCP's quality is unproven.** Only the *path* is shipped. The hard parts — reliably
  catching sophisticated-wrong claims, expansion shaped to your taste — are deferred. Plumbing: done.
  Judgment: not yet.
- **No cross-project entity resolution or retroactive indexing.** No shared embedding space, no shared
  ID namespace, and nothing indexes Research_MCP's clean, fully-provenanced essays or its silent-log
  into the KG/vector store.
- **No global metering or budget ceiling** across the three systems.
- **Study Phases 3–5 unbuilt** — including Phase 5 "briefing mode, **planner integration**," which is
  the actual hook into the rest of your AI OS. KG hidden-link discovery (Phase 2 Anthropic step) is
  also not implemented.

---

## 6. The ideal combined architecture

**Recommendation: shared *horizontal services*, NOT absorption.**

The literal name "absorption seam" tempts you to fold Research_MCP *inside* podcast-brief
(`core/aggregator/research-mcp/`). **Don't.** Read the same specs more carefully: Research_MCP is a
*standalone MCP server*, "internal callers use the Python client, external callers use MCP," and its
Phase 2 explicitly serves *"podcast, research, **study**."* That is the description of a **shared
horizontal capability**, not a component owned by one vertical app. The "absorption seam" was a
Phase-1 *de-risking test* ("can this be relocated cleanly?"), not a commitment to bury it inside the
podcast pipeline. Folding a horizontal service into one vertical would lock research away from the
study system — the exact opposite of what you want.

```
        VERTICAL APPS  (each consumes the shared services)
        ┌───────────────┐   ┌───────────────┐
        │ podcast-brief │   │ study system  │   ...future OS apps
        │ (pod → brief) │   │ (vault→cards) │   (planner, chrome plugin, …)
        └──────┬────────┘   └──────┬────────┘
               │ Python client     │ MCP / Python client
               ▼                   ▼
        ┌───────────────────────────────────┐
        │  RESEARCH / AGGREGATOR SERVICE     │   ← Research_MCP, kept standalone
        │  triage → expand → fetch →         │
        │  dedup → annotate → synthesize →   │
        │  citation-gate                     │
        └──────┬─────────────────────┬───────┘
               │ writes provenanced  │ reads / writes
               ▼                     ▼
        ┌───────────────────────────────────┐
        │  SHARED MEMORY SUBSTRATE           │   ← promoted from study/store/
        │  SQLite + ChromaDB + NetworkX KG   │     + MemoryClient(search_entities,
        │  + unified Entity / Claim / Source │       search_claims, search_sources, …)
        └──────┬─────────────────────────────┘
               ▼
        ┌───────────────────────────────────┐
        │  SHARED LLM GATEWAY + METER        │   ← promoted from Research_MCP MeteredClient,
        │  multi-provider, dated pricing,    │     extended to multi-provider (study's LLMClients),
        │  ONE global budget ceiling         │     ONE correct pricing table
        └───────────────────────────────────┘
        ┌───────────────────────────────────┐
        │  SHARED CONTRACTS (core/contracts) │   ← merge Research_MCP contracts + study types
        │  + unified Entity / Claim / Source │     + ONE entity namespace
        └───────────────────────────────────┘
```

**Why this shape:** each shared layer **deletes a triplicated, partly-broken implementation** and
replaces it with the single best one that already exists — and it gives the cross-references from
fault line §4.2 a place to actually live.

| Shared layer | Adopt the best existing… | …and retire the others |
|---|---|---|
| LLM gateway + meter | Research_MCP `MeteredClient` + dated pricing | podcast's bare SDK calls; study's buggy cost table |
| Contracts / identity | Research_MCP frozen Pydantic, **extended** with a unified `Entity` | podcast `@dataclass`es; isolated study types |
| Research engine | Research_MCP as-is, standalone service | podcast's hardcoded `research/` mix |
| Memory substrate | study `store/` (ChromaDB + NetworkX), **holes fixed** | podcast's planned-but-unbuilt `core/memory/` |

---

## 7. Sequenced integration plan (risk-ordered, with honest leverage)

> **Reality check up front:** only **Phase 1** is shovel-ready. Phases 0 and 2–4 are largely net-new
> or require fixing known holes first. Do not let the clean diagram in §6 disguise that most of this is
> construction, not wiring.

**Phase 0 — Shared contracts + shared metered gateway.** *Lowest risk, immediate payoff.*
Adopt Research_MCP's `MeteredClient` + dated pricing as the one gateway; extend it to OpenAI (the
study system needs it); fix the study cost-row bug (§4.3); add a real, enforced global budget ceiling.
Define a unified `Entity / Claim / Source` contract that the other two model worlds map onto.

**Phase 1 — Wire podcast-brief → Research_MCP. *(THE shovel-ready move.)***
Replace the hardcoded profile mix at `pipeline.py:124-159` and delete the inline-Anthropic comparison
path in `research/{academic,news,books}.py`; call Research_MCP's `verify_claims` via the **internal
Python client**. This is the single highest-leverage step, and it is **already designed** — it is
literally Research_MCP's Phase 1.4 exit criterion. Mind the async boundary (§4.5). Everything after
this is net-new.

**Phase 2 — Stand up the shared memory substrate** from the study system's `store/`. **Fix the holes
first:** implement `retrieve_atomic_facts_for_concept`, stop dropping cross-file triplets, and make
ChromaDB non-optional *for the service* (the study CLI can keep its graceful degradation). Give it the
`MemoryClient` API podcast-brief V3 already names. Point Research_MCP's source cache and silent-log at
it.

**Phase 3 — Cross-project entity resolution + retroactive indexing.** Establish one entity namespace;
index Research_MCP's clean, provenanced essays and silent-log into the KG/vector store (this is "free"
precisely because Phase 1 kept full provenance and gated essays); light up `query_memory` /
`resolve_entity`.

**Phase 4 — study system calls the aggregator over MCP.** The KG becomes genuinely cross-domain: a
podcast claim and a study concept can resolve to the **same node**. This is the point where it stops
being three tools and starts being an OS.

---

## 8. Open decisions for you

1. **Which control flow wins (§4.1)?** Recommended: the two-axis (correctness × effort) engine;
   `profile` degrades to a source-prioritisation hint; podcast-brief's typed-claim extraction is kept
   only where it genuinely helps source selection. *Confirm or override.*
2. **Does the shared memory service make ChromaDB mandatory?** Recommended: yes for the *service*,
   while the standalone study CLI keeps graceful degradation. This forces the §4.4 holes to be fixed
   rather than tolerated.
3. **One monorepo or many repos behind shared packages?** Recommended: keep the repos, extract the
   shared layers (gateway, contracts, memory client) into installable packages each repo depends on.
   This preserves Research_MCP's "standalone + absorbable" property without an actual merge.
4. **How rigorous does study-card grounding become (§4.6)?** Recommended: route study card-generation
   through the same citation gate over time, but don't block Phases 0–2 on it.

---

## Appendix — source traceability

Every claim above is traceable to a file I read:

- **podcast-brief:** `README.md`, `V3_PLAN.md`, `core/pipeline.py` (research mix at lines 124-159),
  `research/academic.py` (`search_semantic_scholar` at :53, bare SDK call at :175, inline prompt at
  :233).
- **Research_MCP:** `Research MCP — Phase 1 Build Plan (v3).md` (§2 tiering, §4 locked decisions, §10
  citation gate, §15 deferred, §16 Phase 2 preview), `IMPLEMENTATION_PLAN.md`,
  `ABSORPTION_SEAM_CHECKLIST.md`, `src/research_mcp/sources/semantic_scholar.py` (async client at :44),
  `src/research_mcp/contracts.py` (model list).
- **study system:** `KG + Vec DB  + study system/OVERVIEW.md` — component map (store/ = ChromaDB +
  NetworkX), LLM model split, and "Known Architectural Risks" #1 (cross-file triplets), #3 (cost
  ceiling), #6 (`retrieve_atomic_facts` returns `[]`), #8 (model-name cost mismatch); workspace
  `CLAUDE.md` (fork() rule, phase routing).
