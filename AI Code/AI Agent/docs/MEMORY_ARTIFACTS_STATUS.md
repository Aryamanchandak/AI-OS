# AI Agent — Memory / Artifacts / Vector Index: Current Status

**Status:** ✅ current as of the 2026-07-08 implementation pass. This doc
replaces reading four separate documents (`MEMORY_ARTIFACTS_DEEPDIVE.md`,
`MEMORY_ARTIFACTS_CONCERNS.md`, `MEMORY_ARTIFACTS_IMPLEMENTATION_PLAN.md`,
`MEMORY_ARTIFACTS_IMPLEMENTATION_REPORT.md`) in sequence to answer "what's
the current state of memory/artifacts?" All four are archived in
`docs/OLD/` with their full reasoning and inline comment threads intact —
read them only if you need the *why* behind a decision below, not to find
out *what the decision is*.

**Companion doc:** still-open design questions (not yet decided, not yet
built) live in `docs/MEMORY_ARTIFACTS_OPEN_QUESTIONS.md`. Net-new parked
features are indexed in `TODO.md`.

---

## The three components, in one paragraph each

- **Artifacts** (`services/artifacts.py`) — a content-addressed bytes
  locker. `put(bytes)` hashes the content (full 64-char SHA-256 now, widened
  from 16), writes `{hash}.bin` + `{hash}.json` (metadata sidecar) under a
  process+thread lock with atomic temp-file-then-rename writes, and returns
  `art:<hash>`. Same bytes twice = free dedup, no-op. Now has `list_ids()`,
  `list_artifacts()`, `delete()`, `clear()`, and `gc(referenced_ids,
  dry_run=True)`.
- **Vector Index** (`services/vector_index.py`) — a plain `IndexFlatIP`
  FAISS index (brute-force cosine similarity; correct choice at this
  project's scale — hundreds to low-thousands of items) plus a parallel
  Python list mapping FAISS's integer positions back to string memory-item
  ids. Rebuilds from `memory.json` from scratch whenever it detects drift,
  rather than patching incrementally. `search()` now accepts an optional
  `min_score` floor (default `None` — opt-in, not yet enabled anywhere).
- **Memory** (`cognition/memory.py`) — the domain layer. Four kinds
  (`fact`, `preference`, `tool_outcome`, `scratchpad`); three write paths
  (`remember()` for ambiguous free text — the only one with an LLM
  classification call; `record_outcome()` for tool results, kind hardcoded;
  `add_fact()` for document chunks, kind hardcoded). Read path is
  vector-search-first, keyword-fallback-only-if-vector-returned-nothing.
  `clear()` now also wipes the vector index and the artifact store.

---

## What shipped (Phases 0–5, 2026-07-08)

| Phase | Item | Status |
|---|---|---|
| 0 | `mcp_server` import fix (memory/artifacts imports only) | **Partial** — fixed; see "still broken" below |
| 1 | `record_outcome` descriptor-discarding bug + dead `result_preview` field + 400B–4KB truncation cliff | **Done** |
| 2 | Classifier `temperature` 1.0 → 0; artifact hash 16→64 hex chars | **Done** |
| 3 | Real `content_type` detection; atomic + locked `artifacts.put()` | **Done** |
| 4 | `min_score` floor mechanism; `kinds=` filter at the main retrieval call site | **Mechanism done, not tuned** (see discrepancy below) |
| 5 | Artifact `list()`/`delete()`/`gc()` (reference-counted, dry-run default); `memory.clear()` now wipes artifacts too | **Done** |

**The real bug that's now fixed (Phase 1):** a tool result big enough to be
offloaded to an artifact used to have its permanent memory descriptor built
*without* the 240-char content preview `action.py` had already computed —
the artifact id replaced the preview instead of sitting alongside it. That
made every large fetched result permanently unsearchable by content, findable
only by tool name/arguments. Fixed: the preview now survives in
`value["raw"]`, and `_format_hits()` (decision.py) reads it. Small results
(≤4KB, no artifact) are now stored in full under `value["raw"]` instead of
being truncated to 120/400 chars with no backup copy.

**Still not fully unblocked:** the MCP subprocess now resolves
`agent.cognition.memory` / `agent.services.artifacts` correctly, but full
startup still fails on a separate, previously-undocumented break —
`mcp_server/tools/knowledge_graph` imports `knowledge_graph.kg_store`, a
module that lives in the unrelated `Database/knowledge-graph` project and is
never put on the path. This was explicitly out of scope for Phase 0 and is
tracked as its own decision (vendor it in / add to path / disable that tool)
in `docs/MEMORY_ARTIFACTS_OPEN_QUESTIONS.md`. **Until it's resolved, no live
end-to-end trace of this system exists** — everything below is verified by
reading code and targeted unit-level checks, not by watching a real run.

---

## ⚠️ Known inconsistency to resolve

`docs/OLD/MEMORY_ARTIFACTS_CONCERNS.md` (Concern 2) records a resolved
decision to **exclude `tool_outcome` from default top-of-run retrieval** —
i.e. `agent7.py`'s per-round `memory.read()` call should pass
`kinds=["fact", "preference"]`, not include `tool_outcome`, because nothing
in the current single-loop architecture reasons across runs well enough to
make a prior run's tool result a safe default input to this run.

What actually shipped (Phase 4b, confirmed in
`docs/OLD/MEMORY_ARTIFACTS_IMPLEMENTATION_REPORT.md`) is:
```python
kinds=["fact", "preference", "tool_outcome"]
```
— which still **includes** `tool_outcome`. The bounded Phase 4b change was
"pass *some* explicit `kinds=` instead of none," not "implement the
exclude-`tool_outcome` stance." So the cross-run bleed problem this was
meant to close (a stale tool result from an unrelated prior run outranking
something relevant to the current query, purely on cosine proximity) is
**still live** — the code was made more explicit about what it retrieves,
but not narrowed to the philosophically-resolved default.

This needs an explicit decision: either update `agent7.py`'s `kinds=` to
drop `tool_outcome` (matching the recorded resolution), or revisit and
re-record the resolution if `tool_outcome` inclusion was actually intended.
Tracked in `docs/MEMORY_ARTIFACTS_OPEN_QUESTIONS.md`.

---

## Decisions already made (condensed — see archived CONCERNS.md for full reasoning)

- **Fact volatility:** durability is decided by whether content carries a
  date that can pass, not by fact category. Hard expiry (drop past
  `expires_at`), not soft decay, chosen for simplicity — soft decay can come
  later if needed. The LLM classifier sets `expires_at` as a fifth field on
  its existing structured-output call (no new LLM round-trip). **Not yet
  implemented in code** — this is a decision, not a shipped feature; see
  Open Questions.
- **Cross-run bleed:** durable facts/preferences should carry over between
  runs by default; `tool_outcome` should not, absent a cross-run planner
  that can actually reconcile prior tool results against the current goal
  (none exists today). See the inconsistency flagged above — this decision
  isn't fully reflected in code yet.
- **Fact/preference/scratchpad taxonomy:** not being formalized further.
  Tripwire only — revisit if a live trace shows a concrete misclassification
  that actually caused a problem.
- **Artifact directory / dedup-by-input:** worth having eventually, but must
  only ever *offer* reuse to the LLM, never silently substitute or block a
  fetch. Mechanism (`list()`) shipped in Phase 5; the reuse *policy* itself
  is not designed or built.
- **Hybrid/RRF retrieval:** not being built now. Cheaper guards first
  (min-similarity floor, already shipped as a mechanism in Phase 4; keyword
  fallback when vector is weak, not yet wired in) — measure after those land,
  decide on full RRF later.
- **Write-everything, filter-on-read:** kept, deliberately, for now. Revisit
  only if a live trace shows the store degrading answer quality.
- **`_index()` full reload on every read:** parked as a non-issue at current
  scale; an in-process cache would reintroduce cross-process staleness risk
  against the `mcp_server` subprocess's independent writes. Revisit only if
  profiling shows real cost.
- **Auditability:** flagged as the single cross-cutting gap that touches
  every concern above (no record anywhere of *why* the system classified,
  expired, or GC'd something). Not built. Bake minimal audit logging into
  each mechanism above at build time, rather than retrofitting later.

---

## Verification performed (Phase 1–5, static + unit-level)

- Syntax compiles for `src/agent`.
- Targeted runtime checks passed for: tool-outcome descriptor preview with
  artifact id, `raw` storage for artifact and non-artifact outcomes, legacy
  `result_preview` display fallback, text/non-text content-type detection,
  full-length artifact ids, artifact put/get/meta/list/delete/gc, vector
  `min_score` filtering.
- The sibling MCP knowledge-memory tool now resolves
  `agent.cognition.memory` / `agent.services.artifacts` correctly.
- No repo test suite exists yet (`pytest` collects zero tests) — everything
  above was checked with one-off scripts, not committed tests.

## Remaining follow-up

1. Decide how to handle `knowledge_graph.kg_store` so full MCP startup
   succeeds (blocks all live verification).
2. Resolve the `kinds=` inconsistency flagged above.
3. Run live agent traces once MCP startup is fully fixed.
4. Log real vector similarity scores; only then pick and enable a
   `min_score` threshold (currently unset).
5. Add a real test suite if this repo keeps evolving.
