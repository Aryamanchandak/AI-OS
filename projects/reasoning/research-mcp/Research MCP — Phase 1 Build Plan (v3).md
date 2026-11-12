# Research MCP — Phase 1 Build Plan (v3, HANDOFF)

**Status:** Ready for Sonnet. Complete standalone spec — Sonnet gets only this file + `trusted_sources.yaml`.
**Supersedes:** v1, v2, the Concerns doc.
**Scope:** Phase 1 only. Phase 2 (shared index) previewed, not specified.

---

## 0. What changed from v2 (the two real fixes)

1. **The Brave whitelist is now a real authored file** (`trusted_sources.yaml`), not an assumption inherited from memory. The source matrix and `trusted_sources_only` semantics point at it (§6).
2. **Triage was rebuilt on two axes.** v2 treated "wrong" as if wrong ⇒ easy. The dangerous claims are *sophisticated and wrong* — confidently stated, plausible, false. Those need the same deep machinery as a research topic, pointed at refutation. Correctness and effort are now **independent** (§1.1). This is a control-flow change to the engine core, which is why it had to land before handoff.

---

## 1. The adaptive engine

One pipeline. Stages are conditional — the engine decides which to run per input. The governing idea:

> **Triage everything → stay silent on what's fine → correct what's wrong → research what's deep.**
> Restraint is the feature, not a side effect.

### 1.1 Triage runs on two independent axes

Not one axis (fine / wrong / deep). **Two:**

- **Correctness** — is it true? `true` / `false` / `topic` (n/a — it's a subject, not a claim).
- **Effort** — how much external evidence the *response* needs: `silent` / `light` / `deep`.

Effort is driven by **complexity AND triage confidence**: if Sonnet can't confidently judge correctness from its own knowledge, that low confidence *itself* escalates effort. This is the mechanism that catches sophisticated-wrong: the engine suspects falsehood but won't assert it without evidence, so it routes deep and refutes with real sources.

The quadrants this produces:

| | trivial | sophisticated / low-confidence |
|---|---|---|
| **true** | `silent` — log, don't surface | `deep` exposition — surfaced because it's *rich*, not wrong |
| **false** | `light` correction (≥1 source to cite) | `deep` **refutation** — same machinery as a topic, pointed at the rebuttal |

"Wind turbines are giant fans" = false + trivial → light. "The Jevons paradox makes AI-efficiency regulation pointless" = false + sophisticated → deep refutation. "What is neuromorphic engineering" = topic → deep exposition.

**Precision point (resolves a latent v2 contradiction):** triage *judgment* is always cheap (Sonnet, from the claim text + model knowledge). But any **surfaced** correction must cite — so even a trivial-wrong claim costs ≥1 light fetch to anchor its correction. Only the `silent` path (true + trivial) genuinely fetches nothing. "Zero cost" was only ever true for silence.

### 1.2 Control flow

```
INPUT (a topic, or a brief's claims)
   │
   ▼
TRIAGE  (Sonnet · on EVERYTHING) → per item: {correctness, effort, confidence}
   │
   ├─ effort = silent (true+trivial) ──► SILENT LOG  (logged, not surfaced)
   │
   ├─ effort = light  (false+trivial / simple check) ──► fetch ≥1 source
   │                                                     → SYNTH-refutation (Sonnet) → CITATION GATE → SURFACE
   │
   └─ effort = deep  (sophisticated, low-confidence, or topic) 
                       ──► EXPANSION (Opus) → proxy searches per facet
                           → FETCH (SourceClients, HTTP) → DEDUP → ANNOTATE (Sonnet)
                           → SYNTHESIS (Opus):
                                • correctness=false → refutation prompt
                                • topic / true+rich → exposition prompt
                           → CITATION GATE (deterministic) → SURFACE
```

**Two entry points, same engine:**
- **`research_topic`** — biased to depth; has a *floor* (always `deep`, always exposition).
- **`verify_claims`** — full *range*; triage assigns effort per claim. Most are silent/light; a sophisticated claim escalates into the identical deep path, refutation-flavoured.

Correction is **not** a cheap side-channel. It's the deep path with a refutation prompt, run at whatever depth the claim's effort demands.

---

## 2. Model tiering (resolved)

Opus is **not** the per-call router. Opus is the **expansion** stage, invoked only on `deep`.

| Stage | Model | When |
|---|---|---|
| Triage | Sonnet | Always, every item |
| **Expansion** (decompose → proxy searches) | **Opus** | `deep` only |
| Fetch / crawl | none (HTTP) | when expansion produced searches, or a light fetch |
| Annotation | Sonnet | once per logical source (only when fetched) |
| Synthesis — deep (exposition or refutation) | Opus, single call | `deep` |
| Synthesis — light correction | Sonnet | `light` |

Plain API fetching is HTTP, no LLM, ~free. (Haiku page-parsing only earns a slot for unstructured pages — avoided in Phase 1, see §15.)

---

## 3. Expansion — the stage worth Opus

A bad router treats the input as the query. A good one treats it as a *brief* and decomposes it.

> "What is neuromorphic engineering?" must not return a definition. It surfaces origins (Mead's analog VLSI), the intellectual lineage, mechanism (how/why), state of the art (Loihi, TrueNorth, spiking nets, memristors), open problems — **each its own proxy search.** That decomposition is the product.

The same stage serves refutation: a sophisticated-wrong claim is decomposed into the sub-questions whose answers establish the rebuttal.

**Phase 1 builds the seam, not the world-model.** Expansion is a distinct stage with its own versioned prompt. Today: a competent Opus decomposition. Later: it grows a model of *how AC2 likes a topic unpacked* without re-architecting. The slot exists now; intelligence fills it over time.

---

## 4. Locked decisions (consolidated)

**From v1:** Option C (unified index, federated artifacts); no semantic memory in Phase 1; standalone repo, absorbable into `core/aggregator/`; free/open sources only; local stdio MCP; SQLite + on-disk run dirs; internal callers use Python client, external use MCP.

**From the Concerns doc:**
- `profile` = domain only → source prioritisation. `depth` removed (engine decides).
- `claim_type` removed (engine infers). Coverage via the source-capability matrix (§6), not a parameter.
- `annotations` = separate table, FK to logical source.
- `claims` simplified: `claim_text`, `verdict`, `confidence`, `run_id`, `timestamp`.
- `trusted_sources_only` tri-state (`None`/`True`/`False`), consulting `trusted_sources.yaml` (§6). Exposed in UI.
- Rate-limit backoff from the start in 1.1.
- Latency is **not** a hard constraint — "anytime" is fine.
- Absorption seam tested during Phase 1 (real dry-run move).

**From iteration:**
- One adaptive engine; **two-axis triage** (§1.1); surface-only output; silent items logged.
- Tiering per §2; no critique loop in Phase 1 (deferred behind measurement, §11).
- Each source its own `SourceClient` behind one interface, exposed as its own MCP tool.
- Dedup to logical sources **before** annotation (§9).
- Reliability bar = **verdict-label stability**, not determinism; low temperature.
- **Citation gate** = hard, deterministic invariant (§10).
- Query cache **dropped** in Phase 1 (semantic cache returns in Phase 2).
- `verify_claims` batches **by brief**.

---

## 5. MCP surface (Phase 1)

**Engine tools:**
- `research_topic(topic, profile?, trusted_sources_only?)` → `run_id` (async).
- `get_run_status(run_id)` → status.
- `get_run_result(run_id)` → `ResearchResult`.
- `verify_claims(brief, trusted_sources_only?)` → `BriefReview` (batched over the whole brief).

**Source tools** (each implements one `SourceClient` interface):
`search_semantic_scholar`, `search_arxiv`, `search_brave`, `search_wikipedia`, `search_google_books`.

Adding a source = new `SourceClient` + tool registration; the engine doesn't change. Subscription/headless-browser sources slot in here later. `query_memory` / `resolve_entity` are absent until Phase 2.

---

## 6. Source-capability matrix + the whitelist

A small static table handed to the engine so a *typeless* input still routes correctly:

| Source | Content | Freshness | Domain filter |
|---|---|---|---|
| Semantic Scholar | academic papers | medium | by field |
| arXiv | preprints (sci/ML/physics) | high | by category |
| Wikipedia | general reference | slightly stale | none |
| Google Books | books | low | none |
| Brave | open web — catch-all for non-academic (fashion, finance, geopolitics…) | high | by domain, via `trusted_sources.yaml` |

**`trusted_sources.yaml`** is the authored whitelist (tiered: `primary` > `press`; categorized by claim domain; plus a `cross_domain` always-trusted tier of wire services / fact-checkers / encyclopedic). It wires to the tri-state:
- `None` → open web unconditionally; no auto-constraint by domain. Caller must explicitly pass `True` to restrict to trusted sources.
- `True` → constrain Brave to the matching category + `cross_domain`.
- `False` → ignore the list.

Known limits inherited from the file: it does **not** fix recency (live prices/breaking news still a Phase-1 gap), some strong sources are paywalled (snippet-only → lower confidence), and the `deny` list is user-authored.

---

## 7. Data contracts (write first, freeze before stages)

Pydantic. Contracts before code.

- **`SourceRecord`** — `source`, `external_id`, `title`, `authors`, `published`, `url`, `raw_excerpt`, `content_hash`, `fetched_at`, `provenance` (query + source tier).
- **`LogicalSource`** — dedup unit (§9): `id`, `fingerprint`, `external_ids` (set), merged metadata, `raw_excerpt`. Annotation iterates over these.
- **`TriageResult`** — per item: `correctness` (true/false/topic), `effort` (silent/light/deep), `confidence` (0–1), `rationale`.
- **`Annotation`** — FK to logical source: `relevance`, `key_findings`, `credibility_tier`.
- **`RunRecord`** — `run_id`, `mode`, `input`, `status`, `created_at`, `finished_at`, `cost_usd`, `model_calls` (§8).
- **`ResearchResult`** — `run_id`, `essay_path`, `logical_sources`, `cost_usd`.
- **`ClaimVerdict`** — `claim_text`, `verdict` (supported/contradicted/mixed/insufficient), `confidence`, `run_id`.
- **`BriefReview`** — `surfaced` (corrections + researched items, each cited), `passed_count`, `run_id`. Silent items logged, not in `surfaced`.

---

## 8. The meter — observable LLM wrapper (built FIRST)

Every model call goes through one wrapper. **Dual storage:**
- **JSONL audit file** — one line per call, kept forever, greppable.
- **`RunRecord.model_calls`** — indexed summary in SQLite for fast queries.

Per-call schema:
```json
{ "timestamp":"...", "model":"...", "stage":"triage|expansion|annotation|synthesis|correction",
  "tokens_in":0, "tokens_out":0, "cost_usd":0.0, "run_id":"...", "status":"success|error" }
```
Cost = `tokens_in·in_price + tokens_out·out_price` from a **dated, versioned pricing table** (historical runs cost at price-at-time; pull current rates live at build time, don't hardcode).

Built in 1.0 so every later stage is metered from its first run.

---

## 9. Dedup → logical sources (before annotation)

Same paper arrives via Semantic Scholar (DOI), arXiv (arXiv id), Brave (URL): three IDs, one paper. Annotating thrice wastes Sonnet. Pre-annotation:

1. **Normalize IDs** — lowercase DOI; arXiv id minus version suffix; URL minus tracking params.
2. **Content fingerprint** — hash of `normalize(title) + first_author + year` (catches the no-shared-ID case); body hash where full text exists.
3. **Group & merge** — map `fingerprint → LogicalSource`; a record whose fingerprint *or* any ID already maps gets its ID *attached* rather than spawning a new row.

**Schema:** one `sources` row per logical source + a `source_ids` table (or JSON column). Unique constraint = **per-fingerprint**. Sources table checked *first* before any API call — it's a **receipt drawer / dedup cache**, not the evidence source.

> In Phase 1 (no memory) the table starts empty, so `verify` is **not** a table lookup: triage → if evidence needed, check table to avoid re-fetch, else fetch fresh.

---

## 10. Citation gate (hard, deterministic invariant)

"Always cite" becomes enforced, not hoped.

**Make citations exist.** Synthesis never sees free-floating text. Each logical source carries a stable id (`S1`, `S2`…) + excerpt. Prompt requires: every factual sentence ends with a `[Sn]` tag; every quotation copied verbatim. Output contains explicit `[Sn]` anchors.

**Verify they're real** (before a run is marked done; no model):
- Every **direct quote** must be a substring of `Sn`'s stored excerpt (whitespace/quote-normalized). Absent → hallucinated → **fail the run**.
- Every **`[Sn]`** must reference a source actually in this run.
- Factual-looking sentences with no anchor → flagged.

A run cannot complete with an unverifiable citation. Applies to corrections too — including light ones (hence ≥1 fetch). Keeps Phase 2 indexing clean.

---

## 11. Cost: measure before optimizing

Phase 1 deep synthesis = **one straight Opus call**. The critique loop (Sonnet-draft → Opus-critique → Sonnet-revise) is **not** built. Build the meter (§8), run ~10 real deep runs, read the number. Then exactly one is true: cost fine → do nothing; cost hurts, quality fine → try the loop; quality weak → fix the prompt. A measured optimization with an off-ramp, not a foundational guess.

---

## 12. Output & restraint

- **`research_topic`** → cited exposition essay on disk + `ResearchResult`.
- **`verify_claims(brief)`** → `BriefReview`: only **surfaced** items — corrections (false, at whatever depth) and researched ideas (true + rich) — plus a quiet **passed_count**. Silence on the fine ones is the point.
- **Silent items logged** to a queryable record (`{claim, correctness:true, effort:silent, rationale, run_id}`), not surfaced. This log is Phase 2's labeled data and the only way to audit *why* the engine stayed quiet.

---

## 13. Ground rules (Sonnet handoff contract)

1. Contracts (§7) frozen before any stage is coded.
2. Typed everything, Pydantic at every boundary.
3. All LLM calls through the meter (§8).
4. Prompts as versioned files: `prompts/triage.md`, `expansion.md`, `annotation.md`, `synthesis_exposition.md`, `synthesis_refutation.md`.
5. Every artifact carries provenance to the exact `SourceRecord`.
6. Idempotent (`INSERT OR IGNORE`), atomic (temp + `os.rename`) writes.
7. No destructive ops — archive, never delete (cache is the only ephemeral exception).

---

## 14. Phase 1 roadmap (phase-gated; validate on real data before advancing)

**1.0 — Scaffold + contracts + the meter.** Repo layout (absorbable into `core/aggregator/`), §7 contracts, observable wrapper (§8) + dated pricing table, MCP skeleton with typed stubs.
*Exit:* server starts; tools return typed stubs; every call metered; contracts frozen.

**1.1 — Source clients + storage + dedup.** Five `SourceClient`s + per-source tools; rate-limit backoff; SQLite; sources-table-first lookup; logical-source dedup (§9); load `trusted_sources.yaml`.
*Exit:* a real query fetches + persists deduped logical sources from all five with provenance; re-run idempotent; a known duplicate paper collapses to one logical source.

**1.2 — Two-axis triage + expansion.** Sonnet triage emitting `{correctness, effort, confidence}` with confidence-driven escalation; Opus expansion (own prompt) on `deep`.
*Exit, all three must hold:*
- "wind turbines are giant fans" → false + light, minimal fetch.
- "neuromorphic engineering" → topic + deep, multi-facet proxy searches.
- a sophisticated-wrong claim (e.g. the Jevons example) → false + **deep**, routed to refutation — **not** waved through as light.

**1.3 — Annotation + dual-mode synthesis + citation gate + `research_topic` E2E.** Sonnet annotation per logical source; single Opus synthesis with **exposition vs refutation** prompts; citation gate (§10). **Run ~10 real deep runs, read metered cost** (§11).
*Exit:* a real topic produces a citation-anchored exposition essay that passes the gate; a refutation run passes the gate too; per-run cost recorded; cost decision logged.

**1.4 — `verify_claims` (batch-by-brief) + podcast wiring + surface-only output.** Whole-brief triage; corrections cited; silent log; podcast swaps its inline research path for the internal Python client.
*Exit:* a real podcast brief returns a `BriefReview` surfacing only false/rich items with provenance, logging the rest silently, rendering end-to-end in one brief.

**Absorption-seam test** runs as a dry-run filesystem+import move during 1.x: relocate to `core/aggregator/research-mcp/`, confirm imports/paths/config hold, document the one-checklist diff for Phase 2.

---

## 15. Deferred (with explicit off-ramps)

- **Synthesis critique loop** → only if 1.3 metered cost says so.
- **Triage judging *well*** — reliably separating sophisticated-wrong from sophisticated-right, and calibrating effort/confidence. Phase 1 ships the *path*; a Sonnet triage will catch obvious wrong claims and miss subtle ones. Same world-model deferral as expansion. **The seam (two-axis routing) is built now because it's control flow — cheap now, expensive to retrofit.**
- **World-model expansion** (proxy searches shaped by AC2's preferences) → the §3 seam grows into this.
- **Semantic query cache** → Phase 2, with embeddings.
- **Subscription / headless-browser sources** → new `SourceClient`s; interface already accommodates them.

---

## 16. Phase 2 preview (NOT in scope)

Connect to existing **ChromaDB** (resolve one-collection-per-project → shared/cross-collection) and **NetworkX KG** (register aggregator entities; reconcile edge types). Light up `query_memory`/`resolve_entity` across podcast, research, study. **Retroactively index** all Phase 1 artifacts + the silent log — free, because Phase 1 kept full provenance and gated (clean) essays.

---

## 17. Open items (resolve at their gate; none block handoff)

- Real **SS↔arXiv overlap rate** on a technical query — confirm the fingerprint actually collapses the duplicate (else you pay to annotate the same paper twice). Near-zero for non-technical topics.
- Tune **triage confidence thresholds** on real claims (this is the deferred "judging well" — expect to iterate).
- Validate **backoff** under real free-API load.
- Curate **`trusted_sources.yaml`** to your own standard; populate `deny`.
