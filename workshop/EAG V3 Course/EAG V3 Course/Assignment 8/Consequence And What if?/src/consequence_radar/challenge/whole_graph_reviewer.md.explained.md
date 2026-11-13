# `challenge/whole_graph_reviewer.md`

Five-line system prompt for a holistic, self-contained cleanup pass over the whole causal graph — distinct from the challenger/adjudicator pair in that it produces graph edits directly rather than going through a separate finding-then-ruling cycle.

## Role in the pipeline
Consumed by `whole_graph_review()` in `challenge/__init__.py`, run once per pipeline run, after the quantification-gap patch and before `challenge()`/`adjudicate()`. Unlike the challenger (destructive-only, must not repair) and the adjudicator (rules on someone else's findings), this prompt is told to "review the complete Indian-equity causal DAG end-to-end, then return only necessary `GraphPatch` operations" — it does its own reviewing and its own fixing in one call. The pipeline (`pipeline/__init__.py`) applies the resulting patch itself with `apply_patch(..., require_indian_path=True)`, only if `review_patch.operations` is non-empty.

## Expected inputs
`whole_graph_review()` sends JSON with two keys: `graph` (full `CausalGraph`) and `claims` (list of `EvidenceClaim`) — no `research_failures` field here, unlike `challenge()`.

The prompt's checklist is structural/global rather than adversarial: whether any single transition "does too much work" (i.e. an edge is skipping steps), whether the India route is real and specific, whether time horizons/units are consistent, whether a premise got silently promoted to a stated fact, whether a material assumption needs to be split into a branch, and whether terminal outcomes are concrete. It explicitly rejects cycles and direct "news-to-stock-price" leaps (i.e. an edge that jumps straight from a news node to a market outcome without an intermediate mechanism). Notably it says to "return no operations when coherent" — an empty-operations response is a valid, expected "everything looks fine" result, not a failure — and to record any residual limitations in `remaining_gaps` rather than forcing a graph edit to paper over them.

## Demanded output format
Structured JSON matching `GraphPatch` directly (`{"operations": [...], "reason": ..., "evidence_ids": [...], "remaining_gaps": [...]}`) — the model client enforces this via `response_json_schema`.

## Downstream consumer
`whole_graph_review()` itself does no post-processing; it returns the parsed `GraphPatch` untouched. The caller, `pipeline/__init__.py`, checks `if review_patch.operations:` before doing anything — applying via `consequence_radar.graph.apply_patch(graph, review_patch, self.settings, require_indian_path=True)`, saving a graph revision, and persisting the updated graph artifact. If the patch has no operations, the graph is left as-is and the pipeline proceeds straight to the `challenge` stage.
