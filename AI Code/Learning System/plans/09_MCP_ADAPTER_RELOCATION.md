# MCP Adapter Relocation — Change Record

**Date:** 2026-07-18
**Supersedes:** `plans/08_MCP_SURFACE_RECONCILIATION.md`'s "keep both, standalone is secondary"
compromise. Read that document for background on why two exposures existed in the first place;
this document records why one of them was then removed entirely rather than merely deprioritized.
**Scope:** MCP code location only. No change to `core/`, `automation/generate.py`, the shell
launcher, the four-table schema, or `StudyBaseline`/`config/baseline.json` — those are unaffected
and still live in this repo.

## 1. What changed

This repo's `src/study_system/mcp/` package — `tools.py` (`StudyMCPTools`, `build_mcp_core`) and
`server.py` (a standalone FastMCP server exposing the ten tools, kept for local/direct MCP-client
testing per plan 08's decision) — has been deleted from this repo and moved into the separate
`mcp_server` project:

| Old location (this repo) | New location (`mcp_server`) |
|---|---|
| `src/study_system/mcp/tools.py` (`StudyMCPTools`, `build_mcp_core`, `_write_key`, `_with_key`) | `tools/study/adapter.py` — ported verbatim, only import paths changed |
| `src/study_system/mcp/server.py` (tool registration + `main()`) | folded into `tools/study/logic.py`, which already held the `mcp_server`-registered tool functions from the plan-08 pass |

Also removed from this repo: the `mcp` SDK dependency (`pyproject.toml`), the `study-mcp` console
entry point, `scripts/run_study_mcp.sh`, and the two tests that exercised the standalone server
(`tests/unit/test_mcp_server.py`, `tests/unit/test_mcp_bootstrap.py` — their coverage was of code
that no longer exists here). `uv.lock` was regenerated (`uv lock`) to drop the now-unused `mcp`
dependency's transitive packages.

This repo is now a pure library: `core/`, `automation/`, `repositories/`, `storage/`, `scheduling/`,
`types/`, and the automation job. It has no MCP code, no MCP dependency, and cannot itself expose
these tools to anything — `mcp_server`'s `study` group is the only way to call them.

## 2. Why go further than plan 08's "keep both, standalone is secondary"

Explicit user instruction: move the MCP code into `mcp_server` rather than maintain a synced copy.
This is also the outcome plan 00 §2 anticipated from the start:

> These are logical boundaries. They can remain in one repository/package initially. If deployment
> later requires physical folders under separate Automation and MCP roots, both adapters should
> import the same versioned core package.

Plan 08 had already established that `mcp_server`'s `study` group was the canonical path the
unified chat agent actually uses; the standalone server in this repo was never called by anything
except local manual testing. Physically relocating the adapter code removes the maintenance burden
of keeping two files in sync (which had already drifted once, per plan 08) at the cost of losing a
same-repo local-test entry point — acceptable, since `mcp_server`'s own server can be pointed at
just this group for local testing if that's ever needed.

## 3. How the move was done

1. Ported `StudyMCPTools`/`build_mcp_core` verbatim into a new `mcp_server/tools/study/adapter.py`
   (no logic changes — only the `study_system.mcp.tools` self-reference removed, since the file no
   longer lives inside that package).
2. Changed `mcp_server/tools/study/logic.py`'s import from
   `from study_system.mcp.tools import StudyMCPTools, build_mcp_core` to
   `from .adapter import StudyMCPTools, build_mcp_core`. No other change to `logic.py` — the tool
   functions it already held (updated in the plan-08 pass) call the same `_get_tools()` singleton
   as before.
3. Verified the relocated code before deleting anything in this repo (see §4).
4. Deleted `src/study_system/mcp/`, the two dependent tests, `scripts/run_study_mcp.sh`, the
   `study-mcp` entry point and `mcp` dependency in `pyproject.toml`, then ran `uv lock`.
5. Updated `CLAUDE.md` and `README.md` in this repo to remove every reference to an in-repo MCP
   surface and point at `mcp_server` instead.

## 4. Verification

Because `mcp_server` has no pytest suite, verified by direct execution, in three steps of
increasing fidelity, all against this repo's real code via the study-system `.venv` (3.11 — system
`python3` is 3.9 and fails on runtime `|`-union evaluation, unrelated to this change):

1. **Direct file-path import of `logic.py`** (fails on relative import — expected, since it's now a
   real package submodule, not a standalone script; documented as a false start, not a bug).
2. **Package-style import (`importlib.import_module('tools.study.logic')`)** — correctly exercises
   the relative import, but pulls in `mcp_server/tools/__init__.py`'s full auto-discovery of every
   *other* group too, which fails on an unrelated pre-existing gap (`tools/documents/annual_report`
   needs `google.genai`, not installed in this sandbox — same class of gap noted in plan 07 §8 for
   `knowledge_graph`/`agent`, not something this change introduced).
3. **Stubbed-parent import** — pre-registered empty `tools` / `tools.study` package objects in
   `sys.modules` (with correct `__path__`) before loading `logic.py`, isolating it from the other
   groups' auto-discovery. This is the same isolation technique plan 07 §8 already used. Result:

   ```text
   IMPORT OK
   progress: {'cards': 0, 'concepts_with_cards': 0, 'due_cards': 0, 'generation_runs': 0,
              'total_concepts': 0, 'unseen_concepts': 0, 'recent_activity': [], 'active_overrides': []}
   due cards: {'cards': [], 'count': 0}
   start_feynman(None) raised as expected: RuntimeError No final-KG concepts are available for automatic selection
   ```

   All function signatures inspected and matched the plan-08 surface exactly.
4. **`tools/study/__init__.py` itself** (the real registration entry point, not just `logic.py` in
   isolation) was also executed with the same stubbing technique, confirming all 12 functions
   register into `tool_registry` under `group="study"` without error.

After deleting the study-system side:

```text
uv run --no-dev --with pytest python -m pytest -q     → 42 passed (down from 44; the two deleted
                                                          MCP tests accounted for the difference)
uv run --no-dev --with mypy python -m mypy src/study_system   → Success: no issues found in 19 source files
uv lock                                                → Resolved 35 packages, no errors
```

grep confirmed no remaining reference to `study_system.mcp`, `study_system/mcp`, `study-mcp`, or
`run_study_mcp` anywhere in `src/`, `tests/`, `scripts/`, or the living docs (`README.md`,
`CLAUDE.md`) — `plans/07`, `plans/08`, and `plans/BASELINE_CAPTURE.md` still mention the old
location as historical record, which is intentional (they are dated verification/capture documents,
not living reference docs).

## 5. Not done in this pass

- No behavior change to any tool — this was a pure code-location move, verified to produce
  byte-identical responses to the pre-move adapter (same source, same logic, different file).
- `mcp_server` still has no automated test suite of its own; the study group's coverage remains
  import/signature/smoke-call verification, not pytest. Worth a follow-up if `mcp_server` ever
  grows one project-wide.
- The standalone local-test path is gone. If local MCP Inspector testing of just the study tools is
  needed again, it would have to run through `mcp_server`'s own server (all groups) or a new
  purpose-built single-group launcher in that project — neither was built here.
