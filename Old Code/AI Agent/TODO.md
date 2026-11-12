# TODO — parked items (deferred on purpose, not dropped)

These were raised during the loop-restructure design (2026-07-06) and
consciously set aside so the core loop can be built first. Each is parked with
enough context to pick up cold. Nothing here is cancelled — it is waiting.

See `docs/LOOP_RESTRUCTURE_PLAN.md` for the core design these hang off.

---

## 1. Research mission (pre-PLAN context gathering)
**Status:** parked — promising, not yet designed.

Before PLAN decomposes a query, the agent should often go gather context first,
rather than plan in a vacuum. Two distinct sub-missions:
- **Personal-context-finder** — pull what the system already knows relevant to
  this query (memory, prior runs, user facts/preferences).
- **Googler / idea-generator** — external research to surface approaches/ideas.

Needs: an enumeration of the *kinds of input this agent will receive*, to know
*when* a research mission is warranted (our tool capabilities are well-defined,
so we can reason about this). Slots in cleanly as a phase in front of
`perception.plan`. Design separately; do not build next to the unsettled core.

## 2. Parallel tool firing
**Status:** parked — needs its own technical review + sign-off (operator will
need help here). Implementation seams stay open in the core so we don't write
the code twice.

- Gateway `chat` already returns `tool_calls` as a **list**
  (`llm_gateway/client.py:13-34`); Decision currently keeps only the first
  (`decision.py:196-204`). The core keeps outputs as a **list of separate
  `GoalResult`s** so fan-out is a later change, not a rewrite.
- **"Independence within a block"** (a term that confused during design): two
  goals are *independent* if neither needs the other's output. Only independent
  goals can fire at the same time. This matters ONLY for parallelism — it is
  NOT needed for correctness (see the core doc: discovery-ordering is handled by
  review *timing*, not by an independence rule). Revisit when parallelism is
  picked up.
- **Verify before shipping parallel:** whether a single MCP `ClientSession`
  over stdio can service concurrent `call_tool`s or serializes them.

## 3. Block-round cap → return to the user with breaks
**Status:** parked — needs more thought.

Instead of a hard cap that silently stops, when the loop has gone too many
rounds it should **break back to the user** (human-in-the-loop checkpoint) for
input, rather than looping or dying. This is a HITL/checkpoint design, not just
a number. For now the core uses a plain hard cap as a placeholder backstop.

## 4. Revisit: decomposition location & Decision autonomy
**Status:** parked — operator wants to look again later.

Under the agreed "hard rails on safety, freedom on strategy" split, *where*
decomposition happens (Perceive vs. a Perceive-brief + Decision-expands two-tier
split) and *how much* Decision may decide on its own are "strategy" questions.
Operator wants to revisit deliberately, not settle by default now.

## 5. Efficiency pass
**Status:** parked by explicit instruction — correctness first.

No efficiency/speed optimization until the loop is correct. Then drill down.

## 6. Operator verification after loop restructure
**Status:** static code review done against the plan doc; live-trace
verification still pending (see below).

Static review (2026-07-06) confirmed the loop wiring, R1-R3, mechanical/LLM
review split, memory refresh timing, and answer composition all match
`docs/LOOP_RESTRUCTURE_PLAN.md`. Two things were found and fixed as part of
that review:
- Artifact-to-goal matching bug — `perception.review()`'s LLM findings carried
  an `artifact_indices` field the prompt asked for but the code never read;
  REVIEW-proposed goals silently fell back to a keyword-overlap heuristic
  instead of PLAN's index-based routing. Fixed: LLM-proposed goals now resolve
  indices like PLAN does, and mechanical retries (unaddressed/error) now carry
  forward the original goal's own `needs_artifact_ids` instead of re-guessing.
- The repeated-identical-tool-call guard in `decision.py` was an undocumented
  4th mechanical rail. Named it R4 in the plan doc §6 and cross-referenced it
  from the code so it isn't a silent mechanism.

A real end-to-end trace is still blocked by two issues in the sibling
`mcp_server` project (outside this repo, unrelated to this restructure):
a known-but-still-live regression where `mcp_server` imports this agent's
`memory`/`artifacts` via a dead path (crashes the whole MCP subprocess, not
just the two knowledge tools as `docs/RESTRUCTURE_PLAN.md` assumed), and a
second, previously-undocumented break where `tools/knowledge_graph` imports a
module that only exists in an unrelated sibling project. Whoever owns
`mcp_server/` needs to fix both before this loop can be run live.

After that's unblocked, verify these design-review loose ends directly in
traces:
- Artifact-to-goal matching correctness (`needs_artifact_ids` routes the right
  bytes to the right goal) — now fixed in code; confirm in a live trace.
- Review's mechanical/LLM split (unaddressed, error, capability_gap are computed
  in code; discovery, insufficient, uncovered come from the LLM pass).
- Context refresh timing (memory is re-read at the top of every round).
- R3 backstop (unavailable tools become `GoalResult(status="capability_gap")`
  without calling Action).
- Final answer composition includes synthesis output plus error/capability-gap
  notes.
- `blocks_so_far` includes the initial block and every review-produced block.
- `goal.done` is written only after an ok `GoalResult`, and is logging-only.

## 7. Deep-dive findings — artifacts, vector index, memory (2026-07-07)
**Status:** design discussion only, nothing fixed. Root cause confirmed for
the mcp_server break (below); everything else is analysis, not yet decided.

**mcp_server import break (root cause, confirmed, not fixed) — this is the
"§6 regression," now pinned exactly:**
- `mcp_server/mcp_server.py` line 23 does
  `sys.path.insert(0, .../"AI Code/agent")` — that directory **does not
  exist** (the agent code now lives at `AI Agent/src/agent/`, a nested
  package, after the restructure).
- Even with the path fixed, `mcp_server/tools/knowledge/memory/tool.py` does
  `import memory as _memory` / `import artifacts as _artifacts` — flat
  top-level imports that no longer match reality (`agent.cognition.memory`,
  `agent.services.artifacts`).
- Confirmed `STATE_DIR` (`src/agent/__init__.py`) is anchored by walking up
  to `pyproject.toml`, not cwd/env — so once import is fixed, the mcp_server
  subprocess and the main agent process resolve to the same on-disk
  `memory.json`/FAISS files. Not the failure mode to worry about.
- Fix shape agreed but **not applied**: retarget the sys.path insert to
  `AI Agent/src` (ideally via the same walk-up-to-sibling pattern
  `gateway.py` already uses, instead of one more hardcoded relative path),
  and change the two imports in `tools/knowledge/memory/tool.py` to
  `from agent.cognition import memory as _memory` /
  `from agent.services import artifacts as _artifacts`. Still needs a
  dry-run inside `mcp_server`'s own `.venv` (separate env from the agent's —
  transitively pulls in faiss/numpy/pydantic/httpx) before trusting it.
- `knowledge_graph`'s tools import `KGStore` from `Database/knowledge-graph`,
  a wholly separate project with its own venv/pyproject. Deliberately kept
  **out** of the above fix — it's a dependency decision (vendor in / add to
  path / disable the tool), not a path typo.

**Artifacts store — real gaps, not hypothetical:**
- No `delete`, `list`, or GC function exists at all. Nothing can even
  enumerate what's in the store today.
- `memory.clear()` wipes `memory.json` + the FAISS index but never touches
  the artifact store — every past `clear()` call has already left 100% of
  referenced artifact bytes orphaned on disk with no memory item left that
  could ever route back to them.
- If per-run artifact deletion gets built (raised by the operator as
  desirable), it will create fresh dangling `artifact_id` references in any
  `tool_outcome` memory item from a prior run — `Memory` is never cleared
  per-run, only `Artifacts` would be. Recommended shape if this gets
  revisited: reference-counted GC (keep anything still referenced by current
  `memory.json`) rather than a blind per-run wipe, which manufactures the
  dangling-reference problem on the very next run.
- `artifacts.put()` has no file locking and no atomic write (unlike
  `memory._save`'s tmp-file-then-rename) — concurrent writes across the two
  processes that share this store aren't crash-safe.
- Artifact IDs are the first 16 hex chars (64 bits) of a sha256 — an
  implicit, undocumented collision-risk assumption. Fine at current scale;
  worth writing down as an accepted limitation rather than leaving it silent.
- `content_type` is hardcoded to `"text/plain"` in `action.py` regardless of
  what the tool actually returned (JSON, HTML, etc.).
- Possible metadata worth adding to `Artifact` (descriptive only, not a
  strict run/goal foreign key, per operator preference): `produced_by`
  (tool/model that generated it), `query_context` (what the user was asking
  when captured), `last_accessed_at`/`access_count` (useful for LRU-style GC
  if built later).

**Memory — the real bug, answers "how is a large thing summarized":**
- `memory.record_outcome()` discards the preview text it's handed whenever
  an `artifact_id` is present:
  `descriptor += f"artifact {artifact_id}"` replaces what would have been
  the 240-char preview computed upstream in `action.py`. This contentless
  descriptor (`"toolname(args) -> artifact art:xxx"`) is the exact string
  passed to the embedder — meaning **any tool result large enough to be
  offloaded to an artifact becomes permanently unsearchable by its actual
  content**, findable only by tool name/argument text.
- `value["result_preview"] = result_text[:400]` is written on every
  `tool_outcome` item but **never read anywhere** — `decision.py`'s
  `_format_hits()` only surfaces `value["raw"]` or `value["chunk"]`. Dead
  field: computed, persisted, never shown to Decision, never embedded.
- Even without an artifact (≤4KB tool result), the permanent descriptor caps
  at 120 chars and `result_preview` at 400 — so content between ~400 bytes
  and 4KB is silently and permanently truncated with no artifact fallback to
  recover it (it wasn't big enough to trigger artifact creation, but too big
  to survive the 400-char cap).
- There is no "is this worth remembering" gate anywhere: every user query,
  every tool outcome, every document-index chunk is written unconditionally
  and kept forever (until an explicit, never-automatically-called
  `memory.clear()`). Worth confirming this "write everything, filter on
  read" bet is intentional rather than assumed.
- `memory.remember()`'s classifier call uses `temperature=1.0` — unusually
  high for a structured-extraction/classification task, and inconsistent
  with `decision.py`'s `temperature=0` for its own (also deterministic-in-
  intent) task. The code already carries a workaround for this exact
  high-temperature failure mode (empty `value` dict → falls back to
  `{"raw": raw_text}`) instead of addressing the likely cause. The comment
  citing the source of this decision (`NOTES_RUNS §6 (2)`) references a
  document that **does not exist anywhere in this repo or the wider `AI
  Code` workspace** — orphaned citation, source reasoning is lost. Worth
  trying `temperature=0` here and checking whether the empty-`value`
  workaround becomes unnecessary.

**Vector index — confirmed correct choice, not a gap:** `IndexFlatIP` (exact
brute-force cosine similarity) is the right call at this project's scale
(hundreds–low-thousands of memory items); approximate indexes (HNSW/IVF)
only pay for themselves at a scale this agent isn't near. `_index()` does
pay a full FAISS-file reload + full list-equality drift check on every
`memory.read()` call — correct, minor inefficiency, parked-tier.

## 8. Direct feature additions — from the deep-dive (2026-07-08)
**Status:** scoped. The deep-dive (`docs/MEMORY_ARTIFACTS_DEEPDIVE.md`) split
into three follow-ups: a sequenced work plan for bounded fixes
(`docs/MEMORY_ARTIFACTS_IMPLEMENTATION_PLAN.md`), open design questions
(`docs/MEMORY_ARTIFACTS_CONCERNS.md`), and the net-new *features* below. §7
above is the raw findings; this §8 is only the things that add a capability
that does not exist yet. Each is tagged with where it's handled.

**Ready to build (policy decided — see the implementation plan):**
- **Artifact `list()` / `delete()`** — no way to enumerate or remove artifacts
  today. Prerequisite for every lifecycle feature below.
  → impl plan Phase 5a.
- **Reference-counted artifact GC** — delete only artifacts nothing in current
  `memory.json` still references; never manufactures a dangling reference.
  Policy decided (ref-count, not blind per-run wipe). → impl plan Phase 5b.
- **`memory.clear()` also clears artifacts** — closes the orphaned-bytes leak
  every past `clear()` has already caused. → impl plan Phase 5c.
- **`content_type` detection on artifacts** — stop hardcoding `text/plain`;
  read the actual MCP content-part type. → impl plan Phase 3a.
- **Minimum-similarity floor on vector search** — a real relevance gate where
  there is none today (mechanism now; threshold from a live trace).
  → impl plan Phase 4a.
- **`kinds=` filtering at `memory.read` call sites** — the `read()` API already
  accepts it; call sites don't use it. Cheap slice of the cross-run-bleed
  problem. → impl plan Phase 4b.

**Shipped (2026-07-09), out of the concerns-doc decisions:**
- **Per-item volatility / expiry on `MemoryItem`** — `expires_at` field added
  to `MemoryItem` and to the classifier's `_Classification` output (5th
  field, same call, no extra LLM round-trip); durable by default, set when
  content is tied to a dated event/deadline. Read paths (`_vector_search`,
  `_keyword_search`) hard-filter expired items out at the same point `kinds`
  filtering happens. Soft decay (score-down instead of drop) was
  deliberately *not* built — hard expiry first because it's simpler; soft
  decay is a real, separate upgrade, tracked below. → concerns doc Concern 1.
- **`tool_outcome` excluded from default run-context retrieval** —
  `agent7.py`'s `RUN_CONTEXT_MEMORY_KINDS` no longer includes `tool_outcome`,
  closing the live cross-run self-conditioning bleed (Phase 4b's cheap
  slice, now applied at the one call site that mattered). → concerns doc
  Concern 2.

**Needs design first (large surface / needs data — see the concerns doc):**
- **Soft-decay scoring for `expires_at`** — score down instead of hard-drop
  as an item ages past expiry; needs a decay curve. Deliberately deferred
  in favor of the simpler hard-expiry cut shipped above. → concerns doc
  Concern 1, sub-question 1.
- **Per-tool default volatility heuristics** (e.g. a weather/price tool's
  outcome is volatile by nature of the tool, independent of the classifier)
  — layered on top of the per-item classifier judgment, not instead of it.
  Deferred until the per-item mechanism (shipped above) is in use and shows
  it's not enough on its own. → concerns doc Concern 1, sub-question 2.
- **Preference overwrite-on-contradiction** — a newly stated preference
  should *supersede* an old one, not just outscore it at read time. Needs a
  lot of nuance (mood/situation-dependent human behavior); explicitly a
  next-phase concern, not needed for the system to function now. →
  concerns doc Concern 1, sub-question 4.
- **Recency weighting / asset-vs-liability curve for `tool_outcome`** — if
  prior tool outcomes are ever reintroduced as an asset at retrieval time
  (not the current default), this is the mechanism that would gate it.
  Parked because without a cross-run planner layer, this architecture has
  no way to act on that information anyway. → concerns doc Concern 2,
  sub-question 1.
- **Run-boundary scoping in Memory** — Memory has no concept of "this run"
  vs. "a prior run" today; facts/preferences get free rein (no scoping)
  deliberately, since the oscillation problem (mood/context-dependent
  preferences) is unsolved and not worth building badly. → concerns doc
  Concern 2, sub-question 3.
- **Artifact metadata enrichment** (`produced_by`, `query_context`,
  `last_accessed_at`/`access_count`) — descriptive fields, useful for a future
  directory / LRU-GC. Descriptive only, not a strict run/goal foreign key
  (operator preference). → concerns doc Concern 4 + §7 above.
- **Dedup-by-input** (don't re-fetch a URL already fetched) — needs a second
  index keyed on input + a freshness policy. → concerns doc Concern 4.
- **Hybrid / RRF retrieval** (run vector + keyword in parallel, merge) — the
  module docstring already names this as a future session; try cheap guards
  first and measure before building RRF. → concerns doc Concern 5.

**Deliberately NOT a feature (decided):**
- No write-time "is this worth remembering" relevance filter — keep
  write-everything/filter-on-read for now. → concerns doc Concern 6.

## 9. Auditability — see what memory/artifacts decided and why
**Status:** parked, but flagged as genuinely important — not a throwaway note.

None of the write-time decisions (classifier kind/expiry judgment, GC
deletions) leave a trace anywhere. If a misclassification or a bad expiry
ever bites, there's currently no way to see *why* the system did what it
did. Shape (not yet designed): log the classifier's raw output alongside
the persisted `MemoryItem`, and log `gc_artifacts()` decisions — not a new
subsystem, just not throwing away what's already computed. Come back to
this once any of the items above (expiry, tool-level volatility, etc.) are
in real use and something needs debugging. → concerns doc Concern 8.
