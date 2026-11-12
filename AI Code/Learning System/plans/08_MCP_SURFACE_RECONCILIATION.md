# MCP Surface Reconciliation — Change Record

> **Superseded the same day by `plans/09_MCP_ADAPTER_RELOCATION.md`.** §2's decision below (keep
> the standalone `study_system/mcp/server.py` as a secondary local-test path) was the state of the
> world for a few hours; it was then replaced by physically moving the MCP adapter/server code out
> of this repo entirely. This document is still accurate for the tool-surface fixes it made
> (auto-select-concept, conversation_so_far, idempotency-key passthrough, the docstring bug) — those
> changes carried forward into the new file location. Read `plans/09` for where the code lives now.

**Date:** 2026-07-18
**Resolves:** `plans/07_MVP_IMPLEMENTATION_VERIFICATION.md` §8 ("Open item for you to reconcile")
**Scope:** MCP tool exposure only. Does **not** touch `automation/generate.py`, the shell launcher,
the four-table schema, `StudyCore`, or any other part of the automation/generation pipeline —
those were already current and are unchanged by this pass.

## 1. Background

Two MCP exposures of the same study-system tools existed:

1. `study_system/mcp/server.py` — this repo's own standalone FastMCP server (`study-mcp` entry
   point, `scripts/run_study_mcp.sh`).
2. `mcp_server/tools/study/logic.py` — a `study` tool group wired into a separate, already-existing
   shared MCP server (`/Users/aryamanchandak/Documents/AI Code/mcp_server`) that also hosts
   `finance`, `knowledge_graph`, `vector_db`, and other groups, and is the server the unified chat
   agent (`AI Agent`, in the sibling `AI Code` workspace) actually connects to.

The shared group (#2) was wired before `study_system/mcp/tools.py` gained `conversation_so_far` and
auto-select-concept (`concept_id=None`) support, so it had drifted behind the standalone server (#1).

## 2. Decision

The shared `mcp_server` project's `study` group is the **canonical, primary integration path** —
it's what the unified chat agent actually calls. The standalone `study_system/mcp/server.py` is
kept only for local/direct MCP-client testing (e.g. the MCP Inspector) and is not the production
path. This was a user decision, not inferred — recorded here so it doesn't need re-deciding.

**Implication for future changes:** any change to `study_system/mcp/tools.py`'s method signatures
must be mirrored in `mcp_server/tools/study/logic.py` in the same pass, or the two will drift again
exactly as they did here.

## 3. What confirmed the scope

Before editing anything, confirmed the unified chat agent (`AI Agent/src/agent/`) has **zero**
study-specific code — no references to `study_`, `flashcard`, `feynman`, or `challenger` anywhere in
its source. This is because `mcp_server.py` auto-discovers every `@register(group=...)` tool via
`tool_registry.get_all()` and hands each one to `FastMCP` generically
(`mcp.tool()(entry.fn)`); the calling agent is a general LLM loop that decides which registered
tool to call from its name and docstring alone. There is no separate frontend code path to update —
**the tool function signatures and docstrings in `logic.py` are the entire UI contract** for this
system, per `plans/00` §6 and `plans/05` §4 (no dashboard/standalone frontend belongs in this repo).
This is why "update the UI" resolved to "fix `logic.py`," not a change in `AI Agent`.

## 4. Changes made

### `mcp_server/tools/study/logic.py`

| Function | Before | After |
|---|---|---|
| `study_start_feynman` | `concept_id: str` (required) | `concept_id: str \| None = None`, `idempotency_key: str \| None = None`. Docstring now states omitting `concept_id` auto-selects a concept, and that the call is deterministic/read-only/safe to repeat. |
| `study_evaluate_feynman` | `(attempt_id, explanation)` — no history | added `conversation_so_far: list[dict[str, str]] \| None = None`, `idempotency_key`. Docstring states study-system holds no session state and the caller must pass every prior turn each call. |
| `study_start_challenger` | `concept_id: str` (required) | same fix as `study_start_feynman`. |
| `study_grade_challenger` | `(attempt_id, answer)` — no history | same fix as `study_evaluate_feynman`. |
| `study_progress` | `() -> dict[str, int]` — no params, **wrong return type** (payload includes lists: `unseen_concepts`, `recent_activity`, `active_overrides`) | `(recent_limit: int = 20) -> dict[str, Any]`; docstring lists the actual return fields. |
| `study_cancel_temporary_override` | `(override_id)` — no idempotency key | added `idempotency_key: str \| None = None`. |
| `study_set_temporary_override` | no idempotency key | added `idempotency_key: str \| None = None`. |
| `study_generate_cards`, `study_get_due_cards`, `study_submit_review`, `study_record_feynman_evaluation`, `study_record_challenger_evaluation` | — | unchanged — already matched `study_system/mcp/tools.py`. |

No signature-name changes, so `tools/study/__init__.py` (which lists the same ten function names for
`register(group="study")`) needed no edit.

### A second, more material bug found while answering plan 07's open annotations

While grounding the "why are start/evaluate two tools" answer in `plans/07` §2–3 against the actual
`StudyCore` code, found that `logic.py`'s module docstring and the `evaluate_feynman`/
`grade_challenger` docstrings were **factually wrong**, not just outdated: they claimed those calls
"do not call an LLM themselves" and always require a follow-up `study_record_*_evaluation` call to
persist. In the current wiring this is false — `mcp/tools.py::build_mcp_core` always constructs
`StudyCore` with `practice_evaluator=GatewayPracticeEvaluator(gateway)` (unconditionally, not gated
on `generation_backend`), and `StudyCore.evaluate_feynman`/`grade_challenger` call that evaluator
(which hits the shared LLM gateway via `structured_chat`) and persist the outcome in the same call
whenever it's set. The response contains `evaluation`/`outcome_id`, not a bare `grading_prompt`.
The `grading_prompt`-only / call-`record_*`-yourself path only happens if `practice_evaluator` is
`None` — a fallback, not the normal flow.

Because these docstrings are the entire UI contract (§3 above), this was actively steering the
calling agent to redundantly self-grade and call `record_*` on every turn, or to be confused when
the response shape didn't match. Fixed by rewriting the module docstring and all four affected
function docstrings (`study_evaluate_feynman`, `study_grade_challenger`,
`study_record_feynman_evaluation`, `study_record_challenger_evaluation`) to describe the actual
dual-mode contract: normal case is graded-and-persisted already; the `record_*` tools are a
gateway-unavailable fallback, keyed off whether the prior call returned `evaluation` or
`grading_prompt`.

### `study-system` documentation

- `CLAUDE.md` — replaced the "⚠️ two exposures need reconciling" warning under the MCP-surface
  section with the resolution above; struck through the corresponding item in "Known Open Items."
- `plans/07_MVP_IMPLEMENTATION_VERIFICATION.md` §8 — replaced the open item with a pointer to this
  document and a one-paragraph resolution summary.

## 5. Verification

The shared `mcp_server` project has no test suite. Verified by direct import/execution against the
real `study_system` package, using the study-system repo's own 3.11 venv (system `python3` is 3.9
and fails on `|`-union runtime evaluation unrelated to this change):

```bash
cd mcp_server
<study-system>/.venv/bin/python3 -c "
import sys; sys.path.insert(0, '.'); sys.path.insert(0, '../Automation Personal/study-system/src')
import importlib.util
spec = importlib.util.spec_from_file_location('study_logic', 'tools/study/logic.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
# ... inspect.signature() on all 12 functions, plus live calls
"
```

Results:

- Module imports cleanly against the current `study_system.mcp.tools.StudyMCPTools`.
- All 12 function signatures inspected and confirmed to match the intended surface above.
- `study_progress(recent_limit=5)` and `study_get_due_cards()` ran successfully against the checked-in
  `config/baseline.json` (no KG/vector configured) and returned the expected empty/zero state.
- `study_start_feynman(None)` raised `RuntimeError: No final-KG concepts are available for automatic
  selection` — correct behavior with no KG source configured, not a bug.

The full shared server (`mcp_server.py`, all groups together) still cannot be started in this sandbox
— pre-existing gap noted in `plans/07` §8, unrelated to this change: the `knowledge_graph` and
`agent` packages it also imports are not installed here.

## 6. Not done in this pass

- No production KG/vector adapter was wired — `study_start_feynman(None)` still fails until
  `kg_concepts_path`/`vector_snippets_path` point at real data (`plans/07` §6, `CLAUDE.md` open item
  2).
- No change to `automation/generate.py`, the shell launcher, or the four-table schema — out of scope,
  confirmed unaffected.
- `mcp_server` changes are made but **not committed** — it's a separate git repository with its own
  history; commit is pending explicit confirmation.
