# Memory / Artifacts / Vector Index Implementation Report

**Written:** 2026-07-08

**Purpose:** record what was touched, what changed, and which part of
`docs/MEMORY_ARTIFACTS_IMPLEMENTATION_PLAN.md` caused each change.

[NOTE: This is a change ledger, not a new design doc. It explains the work in
plain English so you can audit it without reading code.]

---

## Summary

The implementation covered the in-repo parts of Phases 1 through 5 and the
requested Phase 0 import fix in the sibling `mcp_server/` repo.

One thing is still not fully unblocked: the MCP server now gets past the broken
memory/artifact imports, but full startup still fails on the separate
`knowledge_graph.kg_store` dependency. That dependency was explicitly marked
out of scope in Phase 0.

---

## Files touched in this repo

### `src/agent/cognition/memory.py`

**Plan cause:** Phase 1a, Phase 1b, Phase 1c, Phase 2a, Phase 4a, Phase 5b,
Phase 5c.

**What changed:**

- Tool outcome descriptors now always include a real result preview.
- Artifact ids are appended to the descriptor instead of replacing the result
  preview.
- New tool outcome records store the visible preview under `value["raw"]`
  instead of the dead `value["result_preview"]` key.
- Small non-artifact tool results are stored in full under `value["raw"]`.
- Artifact-backed results store a 400-character preview under `value["raw"]`,
  because the full bytes already live in the artifact store.
- The memory classifier temperature was changed from `1.0` to `0`.
- Vector memory reads now accept an optional `min_score` parameter.
- `memory.clear()` now clears memory, the vector index, and artifacts.
- Added `gc_artifacts(dry_run=True)` to delete artifacts that are no longer
  referenced by any memory item.

[WHY THIS MATTERS: Large tool outputs are now searchable by what they actually
said, not only by tool name. Small outputs no longer lose their middle/tail
content. Clearing memory no longer leaves orphaned artifact files behind.]

---

### `src/agent/cognition/decision.py`

**Plan cause:** Phase 1b.

**What changed:**

- Memory hit formatting now reads `value["raw"]` first.
- It also still reads old `value["result_preview"]` records as a compatibility
  fallback.

[WHY THIS MATTERS: New memory records display correctly, and old records do not
silently become unreadable.]

---

### `src/agent/cognition/action.py`

**Plan cause:** Phase 3a.

**What changed:**

- Tool result collapsing now returns both text and a best-effort content type.
- Text MCP parts are still labeled `text/plain`.
- Known non-text MIME types are preserved when present.
- Unknown non-text parts are labeled `application/octet-stream` instead of
  falsely calling them text.
- Added a TODO at the non-text fallback because true binary artifact handling
  still needs a bytes-preserving path.

[WHY THIS MATTERS: Current text tools behave the same, but future non-text
tools will no longer be silently mislabeled as plain text.]

---

### `src/agent/services/artifacts.py`

**Plan cause:** Phase 2b, Phase 3b, Phase 5a, Phase 5b, Phase 5c support.

**What changed:**

- Artifact ids now use the full 64-character SHA-256 digest instead of the
  first 16 hex characters.
- `put()` now writes under a process lock and thread lock.
- Artifact bytes and metadata are written through temp files and atomic replace.
- Added `list_ids()`.
- Added `list_artifacts()`.
- Added `delete(artifact_id)`.
- Added `clear()`.
- Added `gc(referenced_ids, dry_run=True)`.

[WHY THIS MATTERS: The artifact store is now safer under concurrent writes, has
a stronger collision margin, and finally has lifecycle operations.]

---

### `src/agent/services/vector_index.py`

**Plan cause:** Phase 4a.

**What changed:**

- `VectorIndex.search()` now accepts optional `min_score`.
- Hits below `min_score` are filtered out.
- The default remains `None`, so current behavior is unchanged unless a caller
  opts into gating.

[WHY THIS MATTERS: The mechanism for weak-match filtering exists now, but the
actual threshold can still be chosen from live score traces instead of guessed.]

---

### `src/agent/agent7.py`

**Plan cause:** Phase 4b.

**What changed:**

- The main run retrieval call now passes a known `kinds=` filter:
  `["fact", "preference", "tool_outcome"]`.

[WHY THIS MATTERS: The normal run context no longer asks memory for every kind
without stating intent. This is the small bounded filtering change from the
plan, not the larger run-scoping or recency design pass.]

---

## Files touched outside this repo

### `../mcp_server/mcp_server.py`

**Plan cause:** Phase 0.

**What changed:**

- Replaced the brittle path insert pointing at the old dead `agent/` directory.
- Added a workspace-root finder that locates the folder containing both
  `mcp_server/` and `AI Agent/src/agent`.
- Inserts `AI Agent/src` into `sys.path` before tool imports.

[WHY THIS MATTERS: The MCP subprocess can now resolve the real `agent` package
after the repo restructure.]

---

### `../mcp_server/tools/knowledge/memory/tool.py`

**Plan cause:** Phase 0.

**What changed:**

- Replaced flat imports:
  - `import memory as _memory`
  - `import artifacts as _artifacts`
- With package imports:
  - `from agent.cognition import memory as _memory`
  - `from agent.services import artifacts as _artifacts`

[WHY THIS MATTERS: The knowledge tools now import the same memory and artifact
modules used by the main agent.]

---

## Verification performed

### Passed

- Syntax compile passed for `src/agent`.
- Focused runtime checks passed for:
  - tool outcome descriptor preview with artifact id,
  - `raw` storage for artifact and non-artifact outcomes,
  - legacy `result_preview` display fallback,
  - text and non-text content-type detection,
  - full-length artifact ids,
  - artifact put/get/meta/list/delete/gc,
  - vector `min_score` filtering.
- The sibling MCP knowledge memory tool now resolves:
  - `agent.cognition.memory`
  - `agent.services.artifacts`

### Not fully passed

- Full MCP server startup still fails because of:
  - `ModuleNotFoundError: No module named 'knowledge_graph'`

[NOTE: That `knowledge_graph` dependency was explicitly excluded from Phase 0
in the plan. The import fix requested by Phase 0 is done; the remaining failure
is the separate KGStore dependency decision.]

### No tests available

- `pytest` ran, but the repo currently has no test files, so it collected
  zero tests.

---

## Phase-by-phase status

| Phase | Status | Notes |
|---|---|---|
| Phase 0 | Partial unblock | Requested memory/artifact import fix done. Full MCP startup still blocked by out-of-scope `knowledge_graph`. |
| Phase 1 | Done | Preview bug fixed, `raw` made visible, small-result truncation cliff closed. |
| Phase 2 | Done | Classifier temperature set to `0`; artifact hashes widened to 64 hex chars. |
| Phase 3 | Done | Content type detection added; artifact writes locked and atomic. |
| Phase 4 | Mechanism done | `min_score` added as opt-in; `kinds=` filter added. Threshold tuning still needs live traces. |
| Phase 5 | Done as mechanism | list/delete/gc/clear lifecycle added. GC defaults to dry-run for safety. |

---

## Remaining follow-up

1. Decide how to handle `knowledge_graph.kg_store` for full MCP startup.
2. Run live agent traces after MCP startup is fully fixed.
3. Log vector similarity scores from real queries.
4. Pick and enable a `min_score` threshold only after reviewing those scores.
5. Add proper tests if this repo is going to keep evolving.

