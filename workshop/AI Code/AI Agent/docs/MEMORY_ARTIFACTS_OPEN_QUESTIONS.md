# AI Agent — Memory / Artifacts: Open Questions

**Status:** live list of design questions that are decided-in-principle but
**not yet built**, or genuinely undecided. Companion to
`docs/MEMORY_ARTIFACTS_STATUS.md` (what's shipped and what's resolved).
Full original reasoning for each item lives in
`docs/OLD/MEMORY_ARTIFACTS_CONCERNS.md` and `docs/OLD/MEMORY_ARTIFACTS_DEEPDIVE.md`
— this doc only keeps what's still actually open, so it doesn't re-grow into
another 500-line document.

---

## 1. `kinds=` filter doesn't match the resolved cross-run-bleed decision

**Status: needs a decision, blocking nothing else.** See
`MEMORY_ARTIFACTS_STATUS.md`'s "Known inconsistency" section. The recorded
resolution says exclude `tool_outcome` from default top-of-run retrieval;
the shipped code still includes it (`kinds=["fact", "preference",
"tool_outcome"]` in `agent7.py`). Pick one:
- Update `agent7.py` to drop `tool_outcome` from the default `kinds=`, or
- Re-open and re-record the decision if including it was actually intended.

## 2. Fact volatility / `expires_at` — decided, not built

**Decision already made** (hard expiry, LLM-set on the same classifier call
that already produces `kind`/`descriptor`/`keywords`). **Not implemented**:
`MemoryItem` has no `expires_at` field, `remember()`'s classifier doesn't set
one, and nothing in `_vector_search()`/`_keyword_search()` filters on it.
This is the single most consequential item left — it's the root cause behind
Concern 1 (stale facts) and feeds directly into cross-run bleed (item 1
above): an old, confidently-embedded, un-expired fact is exactly what an
unfiltered vector search will surface as its "best" match.

Sub-questions still open even after "hard expiry, LLM-set" is decided:
- Should an expired-but-referenced fact still count toward keeping its
  artifact alive during GC? Leaning toward "drop out" (per your own
  instinct), but this requires building a way to pull content back from an
  artifact when the memory item that pointed to it has expired — that
  retrieval path doesn't exist yet, so dropping out today means the content
  becomes unreachable, not just unlisted. Needs that retrieval path built
  first, or the "drop out" behavior needs to wait for it.
- Per-tool default volatility (e.g. a weather/price tool defaults to
  short-lived) — good idea, explicitly deferred until the per-item mechanism
  above exists and is in use.
- Preference overwrite-on-contradiction (a newly stated preference should
  *supersede* an old one, not just decay against it) — undesigned, flagged
  for a later pass. Genuinely harder than expiry: preferences are
  mood/context-dependent in a way dates aren't, and naive overwrite risks
  losing legitimate situational nuance. Not needed for current functioning.

## 3. `knowledge_graph.kg_store` import still broken

**Blocks all live verification of the memory/artifacts work** (see
`MEMORY_ARTIFACTS_STATUS.md`). `mcp_server/tools/knowledge_graph` imports a
`KGStore` module that lives in the unrelated `Database/knowledge-graph`
project with its own venv; `mcp_server.py` never puts it on the path. Needs
one of: vendor it in, add it to the path, or disable that tool for now.
Whoever owns `mcp_server/` should make this call.

## 4. Artifact directory + dedup-by-input

**Policy decided, mechanism partially shipped, reuse policy not built.**
`list()`/`list_artifacts()` exist now (Phase 5). Still open:
- The dedup key: raw URL? Normalized URL? Tool+args hash? This is a
  *second* index, separate from the content-hash the store already uses —
  content-addressing dedups by output, this would dedup by input (don't
  refetch the same URL twice).
- Freshness window for a cached fetch — proposed to match whatever the
  overall artifact retention window ends up being (same knob, not two).
- Hard constraint already agreed: input-dedup must only ever *offer* reuse
  to the LLM as information ("here's what was already fetched, reuse or
  refetch?"), never silently substitute or gate what the agent can fetch.

## 5. Hybrid / RRF retrieval

**Decided: not now.** Cheap guards first — min-similarity floor (mechanism
shipped in Phase 4, not yet tuned or enabled) plus letting keyword search run
*in addition* when vector confidence is low (not yet wired — today a weak
but nonzero vector hit still blocks the keyword fallback entirely). Only
reach for full RRF if retrieval quality is still the bottleneck after those
two land and get measured against a live trace.

## 6. Auditability (cross-cutting)

**Not started.** No mechanism anywhere logs *why* the system did what it
did — which classifier call decided `fact` vs. `scratchpad`, why an item's
`expires_at` ended up at a given date, why an artifact got GC'd. This is the
one item that touches every other concern above. Recommendation carried over
unchanged: bake minimal audit logging (e.g. log the classifier's raw output
alongside the parsed `MemoryItem`, don't throw it away) into each mechanism
*as it gets built*, rather than retrofitting later.

## 7. `min_score` floor — mechanism shipped, number not chosen

The `min_score` parameter exists on `VectorIndex.search()` (Phase 4a) but is
unset everywhere (`None` = no gating, current behavior unchanged). Don't
pick a number blind — once item 3 above is fixed and a live trace is
possible, log real similarity scores across representative queries, eyeball
where good matches and junk separate, and set the floor from that data.

## 8. Write-everything, filter-on-read — confirmed bet, trigger recorded

Not open in the sense of "undecided" — this is a deliberate, confirmed
choice (every query/tool-outcome/document-chunk written unconditionally,
forever, no write-time relevance gate). Listed here only so the revisit
trigger isn't lost: **revisit only when a live trace shows the store
genuinely degrading answer quality** (relevant hits crowded out by
irrelevant ones that ranking can't fix). Volatility (item 2) and cross-run
bleed (item 1) will likely bite before raw volume does — if answer quality
drops, suspect those first.
