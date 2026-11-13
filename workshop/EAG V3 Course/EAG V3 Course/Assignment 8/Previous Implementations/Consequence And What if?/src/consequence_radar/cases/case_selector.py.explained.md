# `cases/__init__.py`

Runs the final "pick the narrative" LLM stage — asking the model to select one central causal path through the finished graph plus any material alternatives — and then does substantial manual validation of the result before it's allowed to reach the report writer. Most of this file is `validate_cases`, not the LLM call.

## Main entry points

### `select_cases(run_id, graph, claims, model) -> CaseSelection`
Calls `model.generate(..., prompt_name="cases/case_selector.md", schema=CaseSelection, model_tier="reasoning")` with the full graph and claim list as JSON. Immediately runs `validate_cases(selection, graph, {c.id for c in claims})` on the result — there is no retry or repair here; a `CaseSelectionError` propagates straight out uncaught, aborting the pipeline run at this stage. `select_cases` is only ever called once (the pipeline treats this as a single-shot decision, unlike the challenge/adjudicate cycle which has an explicit accept/reject step).

### `validate_cases(selection, graph, claim_ids=None) -> None`
Pure Python, no LLM call, raises `CaseSelectionError` (a `ValueError` subclass) on the first violation found. Builds four lookup structures from the graph first: `edges` (id → `CausalEdge`, excluding only `status in {"rejected", "contradicted"}` — so `"proposed"`, `"supported"`, `"mixed"`, and `"assumption_only"` edges are all still eligible), `nodes` (ids with `status == "active"`, strict equality this time), `assumptions` (id → `Assumption`, unfiltered — `Assumption` has no status field), and `estimates` (ids, unfiltered).

For `selection.central_case`, in order:
1. `central.central` must be `True` — the model has to explicitly mark its own designated case as central, not just be the first one listed.
2. `path_edge_ids` must be non-empty and a subset of the eligible `edges`.
3. `path_node_ids` must be a subset of active `nodes`.
4. `required_assumption_ids` must be a subset of known `assumptions`.
5. `estimate_ids` must be a subset of known `estimates`.
6. If **every** edge along the path has `status == "assumption_only"`, reject it as "depends entirely on unsupported assumptions." This only catches the all-assumption-only case — a path where most edges are assumption-only but one is `supported` passes.
7. The path edges must chain: for every consecutive pair, `left.dst == right.src`. **Gap:** this only checks that the edges connect to each other; it never cross-checks that `path_node_ids` actually corresponds to the node sequence implied by that edge chain. `path_node_ids` is separately required (step 3) to be a subset of active nodes, but two unrelated lists — a correct edge chain and an arbitrary set of active node IDs — would both pass.

Then, for `central_case` and every case in `material_alternatives` (**not** `broken_paths` — that list is never validated here at all):
- If `claim_ids` was supplied (a set of *verified* claim IDs), require `supporting_claim_ids + contradicting_claim_ids` be a subset of it. The inline comment explains why this exists: every other artefact reaching the report gets its claim references checked against verified evidence, but cases previously didn't — an invented claim ID would flow straight into `ReportContext` unchallenged, because the report-side validator only checks `[S..]` source markers, never claim lineage. This check is the fix, but it's conditional: call `validate_cases` with `claim_ids=None` (as the test file does) and this check is skipped entirely.
- `estimate_ids` must be a subset of known estimates (redundant with step 5 for the central case, applied uniformly here for alternatives too).

Finally, for every `material_alternatives` entry: at least one of its `required_assumption_ids` that actually resolves to a known `Assumption` must have `.material == True`, or it's rejected as "not caused by a material assumption." An alternative with an empty `required_assumption_ids` list fails this trivially (`any()` over nothing is `False`).

### `class CaseSelectionError(ValueError)`
The single exception type `validate_cases` raises for every rule above — always with a message naming the specific rule and, where relevant, the offending case ID.

## Connects to
- `consequence_radar.models` — `CaseSelection`, `CausalGraph`, `EvidenceClaim` (request/response shapes), plus `Case` (used implicitly via `selection.central_case`/`material_alternatives`).
- `consequence_radar.providers.model.ModelClient` — the `.generate()` target.
- `consequence_radar.pipeline.__init__` — the sole caller (`from ..cases import select_cases`), invoked once, last in the graph-construction phase, after `adjudicate()` and a final `validate_graph` check — its output (`CaseSelection`) is saved as the `"cases"` artifact and later feeds `ReportContext.central_case` / `.material_alternatives` for the report-writing stage.
