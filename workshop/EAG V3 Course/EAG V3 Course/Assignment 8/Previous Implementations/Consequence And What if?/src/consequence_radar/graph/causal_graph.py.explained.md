# `graph/__init__.py`

This module owns the `CausalGraph` data structure end to end: it validates a graph's structural invariants, applies LLM-proposed patches to a graph under those invariants, and drives the two LLM calls that create a graph from scratch (`build_initial_graph`) and, indirectly through prompt assembly, the incremental patching flow the pipeline uses on every research cycle. It is the only place in the codebase that knows what makes a `CausalGraph` well-formed.

## Main entry points

**`validate_graph(graph, settings, *, require_indian_path=False, claim_ids=None) -> list[str]`**
Returns a list of human-readable problem strings (empty list = valid). It is pure and side-effect free — every other function in the module calls it rather than duplicating checks. What it checks, concretely:

- ID uniqueness within nodes, edges, assumptions, and estimates separately.
- Size ceilings: `settings.max_graph_nodes` (default 24) and `settings.max_graph_edges` (default 36) can't be exceeded.
- Exactly one `active` node with `node_type == "news_seed"` must exist — zero or more than one is an error. "Active" here means `status == "active"`; rejected/superseded nodes are ignored for this and most other checks.
- Every edge's `src`/`dst` must point at a real node id, `mechanism` must be non-blank, and `assumption_ids`/`estimate_ids`/claim-id lists must reference ids that actually exist. The claim-id check only runs when `claim_ids` is passed in (the pipeline passes the accepted-claims id set at later validation points but not at the very first `build_initial_graph` call, since no claims exist yet).
- Assumptions and estimates get the same referential-integrity treatment (`required_for_edge_ids`, `input_estimate_ids`, claim ids).
- The *active* subgraph (rejected edges and edges touching inactive nodes excluded) must be a DAG — built as a fresh `networkx.DiGraph` and checked with `nx.is_directed_acyclic_graph`.
- The news_seed root must have zero incoming edges among active edges.
- Every active node whose type is `company_metric`, `sector_metric`, or `market_outcome` ("outcomes") must be reachable from the seed (`nx.descendants`); unreachable ones are flagged as "orphan outcome".
- A hardcoded structural rule: an edge that goes directly from the `news_seed` node to a `market_outcome` node whose label contains the substring `"stock price"` (case-insensitive) is rejected outright — the graph is expected to route through at least one intermediate causal step, never news → stock price in one hop. This is a very specific, string-matched rule and only fires when the outcome's label literally contains "stock price"; a label like "share valuation" would not trigger it.
- When `require_indian_path=True` (used everywhere except the very first initial-graph build): at least one outcome node must be reachable from the seed *and* be India-tagged — either `geography` contains "india" (casefold) or the node has any `entity_ids`. That target's label can't be one of three hardcoded generic placeholders (`"stock is affected"`, `"company is affected"`, `"share price impact"` — again exact casefolded string match). And every incoming edge into that outcome collectively must carry at least one `estimate_ids` entry, i.e. the outcome must be quantified or explicitly directional, not just narratively asserted.

**`topological_graph(graph) -> CausalGraph`**
Returns a copy of the graph with `nodes` re-sorted: active nodes first in topological order (via the same rejected/inactive-filtered DAG), then all inactive/rejected nodes at the end, sorted by their original topo position (or `10**6` if unreachable/not in the sort, i.e. pushed to the back). This does not touch edges, assumptions, or estimates — it is purely a display/ordering helper. It is consumed by `report_context/__init__.py` (`compile_context` uses `topological_graph(graph)` when building the `ReportContext.graph` field), not by the main pipeline loop.

**`apply_patch(graph, patch: GraphPatch, settings, *, require_indian_path=False) -> CausalGraph`**
Deep-copies the input graph, then applies every `GraphOperation` in `patch.operations` in list order via a big if/elif dispatch on `operation.op`:
- `add_node` / `add_edge` construct a new `CausalNode`/`CausalEdge` from `operation.value` merged with `id=operation.target_id`.
- `update_node` / `update_edge` use the private `_replace()` helper: find the item by id, `model_dump()` it, `.update()` with the patch's `value` dict, then re-validate through the pydantic schema. Raises `KeyError` if the target id isn't found (this propagates uncaught out of `apply_patch` — see failure-path note below).
- `reject_node` / `reject_edge` are shorthand for `_replace(..., {"status": "rejected"}, ...)`.
- `add_assumption` / `update_assumption` / `add_estimate` / `update_estimate` are matched with `op.startswith(...)` rather than `==`. Since `GraphOperation.op` is a pydantic `Literal` already constrained to the exact strings, `startswith` and `==` behave identically here — it reads like leftover code from a time when suffixed variants might have existed, not a functional issue today.

**Bug: the assumption/estimate branches import from the wrong module.** All four of those branches do `from .models import Assumption` / `from .models import Estimate` — a *relative* import meaning "look for a `models` submodule inside the `graph` package itself." No such file exists (`consequence_radar/graph/models.py` is not present; `Assumption`/`Estimate` actually live in `consequence_radar/models/__init__.py`, i.e. `..models`, one level up, which is already imported at the top of this file for the other four model classes but not for these two). Confirmed empirically: constructing a `GraphPatch` with an `add_assumption` operation and calling `apply_patch` raises `ModuleNotFoundError: No module named 'consequence_radar.graph.models'`, not a validation error.

This means any patch the model proposes that adds or updates an assumption or an estimate — a completely normal, schema-legal thing for the `graph_patcher.md` prompt to ask for — will crash `apply_patch` with an unrelated import error instead of being applied or cleanly rejected. Because `pipeline/__init__.py` wraps every `apply_patch` call in a broad `except Exception`, this doesn't crash the run: it's caught, logged as an `invalid_graph_patch` artifact, and treated exactly like a validation failure, triggering the one-shot repair generation. But the repair call re-invokes the same broken code path if the repaired patch *also* touches an assumption or estimate, so the second failure is saved as `invalid_graph_patch` (key `cycle-N-repair`) and the loop simply moves on with the graph unchanged for that cycle — a silent, structural inability to ever add or amend an assumption or an estimate via patch, masquerading as an ordinary validation retry.

After all operations are applied, `result.version` is incremented by exactly 1 (regardless of operation count) and the result is run through `validate_graph`. Any problems raise `GraphValidationError` (defined at the top of the file, `ValueError` subclass carrying `.problems: list[str]`); the caller (pipeline) is expected to catch this and retry with a repair prompt.

**`revise_graph(run_id, graph, patch, settings, model_call_id=None) -> tuple[CausalGraph, GraphRevision]`**
A convenience wrapper: calls `apply_patch`, then builds a `GraphRevision` audit record (before/after version, reason, evidence ids, operations, generated `R<uuid>` id). Note this function is **not called anywhere else in the codebase** — `pipeline/__init__.py` reimplements the identical `GraphRevision`-construction logic inline in its own `_save_revision` method rather than calling this. `revise_graph` is effectively dead/duplicated code from the orchestrator's point of view (it is not imported by `pipeline/__init__.py`, `challenge/__init__.py`, or anything else observed).

**`build_initial_graph(run_id, seed, model: ModelClient, settings) -> CausalGraph`**
The entry point used once per run, right after seed selection. It calls `model.generate(..., stage="initial_graph", prompt_name="graph/initial_graph_builder.md", prompt_data=seed.model_dump_json(), schema=CausalGraph, model_tier="reasoning")` — the seed object (the selected news candidate) is serialized to JSON and handed to the model as the sole input. The returned graph's `version` is force-set to `1` (`model_copy(update={"version": 1})`, overriding whatever the model returned) and validated with `validate_graph(graph, settings)` — note `require_indian_path` is *not* passed here, so the very first graph does not yet need to prove it reaches a quantified Indian outcome; that's enforced later in the pipeline after the research/patch cycles. If validation fails, exactly one repair attempt is made: a second `model.generate` call, same prompt file, `stage="initial_graph_repair"`, `retry_count=1`, with `prompt_data` now containing `{"rejected_graph": ..., "validation_errors": problems}` as JSON instead of the seed. If the repaired graph still fails validation, `GraphValidationError` is raised and propagates to the pipeline's top-level exception handler (marking the run `FAILED`). There is no second repair attempt.

## How the two `.md` prompt files are actually used

Both `graph/graph_patcher.md` and `graph/initial_graph_builder.md` are loaded by path through `providers/model/__init__.py`'s `load_prompt(name)`, which resolves `PROJECT_ROOT / "src" / "consequence_radar" / name` — so the `prompt_name="graph/initial_graph_builder.md"` string passed from this module is literally the file's location relative to the package root. `load_prompt` also reads the first line of the file (`<!-- version: N -->`) as a version tag recorded in the model-call audit log; both files currently declare `version: 1`.

Inside `GeminiModelClient.generate` (`providers/model/__init__.py`), the loaded prompt text and the caller-supplied `prompt_data` string are concatenated as:

```
f"{instruction}\n\n<INPUT_DATA>\n{prompt_data}\n</INPUT_DATA>"
```

and sent as `contents` to `client.models.generate_content(...)` with `response_mime_type="application/json"` and `response_json_schema=schema.model_json_schema()` — i.e. the output shape (`CausalGraph` for the builder, `GraphPatch` for the patcher) is enforced by the Gemini structured-output contract driven by the pydantic schema passed as `schema=`, not by anything written in the prompt text itself. Neither `.md` file mentions JSON, a schema, or a return format explicitly.

**Builder vs. patcher, based on the actual calls in this file:**
- `initial_graph_builder.md` is used only inside `build_initial_graph`, always with `schema=CausalGraph` — it produces a *complete new graph* from a bare news seed, with no prior graph as input. Called once (plus at most one repair) per run, right after seed selection and before any research/evidence gathering happens.
- `graph_patcher.md` is never referenced inside this file at all — it's loaded and used exclusively from `pipeline/__init__.py`, always with `schema=GraphPatch`, and always with an *existing* graph plus new evidence (`tasks`/`claims`, or a `rejected_patch`/`validation_errors` pair for repairs, or a synthetic `{"instruction": ...}` block for the quantification-gap pass) serialized into `prompt_data`. Its output (`GraphPatch.operations`) is fed into this file's `apply_patch` by the pipeline, not by anything in `graph/__init__.py` itself. See `pipeline/__init__.py.explained.md` for the exact call sites.

## Connections

- Imports `CausalEdge, CausalGraph, CausalNode, GraphOperation, GraphPatch, GraphRevision` from `..models` (the shared pydantic schema module) and `ModelClient` from `..providers.model`.
- Consumed by: `pipeline/__init__.py` (`GraphPatch, apply_patch, build_initial_graph, validate_graph`), `challenge/__init__.py` (`apply_patch` — the adjudication step applies accepted challenger patches itself rather than the pipeline doing it), and `report_context/__init__.py` (`topological_graph`, for ordering the graph before it's embedded in the report context).
- `graph/test_graph.py` exercises `validate_graph` and `apply_patch` directly against fixtures defined in the project-root `conftest.py`.
