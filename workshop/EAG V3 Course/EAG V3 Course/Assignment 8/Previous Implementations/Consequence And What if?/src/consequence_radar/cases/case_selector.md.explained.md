# `cases/case_selector.md`

Five-line system prompt for the final narrative-selection stage: picking one central causal path through the finished, challenged, adjudicated graph, plus any alternatives that matter.

## Role in the pipeline
Consumed by `select_cases()` in `cases/__init__.py`, called once, last in the graph-construction phase — after `whole_graph_review`, `challenge`, and `adjudicate` have all run and the graph has passed a final `validate_graph` check. Its output becomes the spine of the eventual report: the "central case" is the story the newsletter is built around.

## Expected inputs
`select_cases()` sends JSON with two keys: `graph` (the full, post-adjudication `CausalGraph`) and `claims` (the accumulated `EvidenceClaim` list from all research cycles).

The prompt instructs the model to choose the central case as "the complete active Indian-equity path with the strongest evidence and fewest unsupported material assumptions," to return alternatives only when a material assumption would change the equity conclusion, and to list broken paths separately from viable alternatives. It requires using only IDs that were actually supplied (node/edge/assumption/claim/estimate), keeping facts/forecasts/assumptions/inferences/estimates distinct (the same recurring rule as every other prompt in this codebase), and treating "most supported" as not certain — no invented probability may be attached to it. It also requires each case to state its required assumptions, its supporting and contradicting evidence, its direction, whether it's quantified or directional-only, a time horizon, and — notably — "the observation that would weaken it" (a falsifiability requirement per case).

## Demanded output format
Structured JSON matching `CaseSelection` (`{"central_case": Case, "material_alternatives": [Case, ...], "broken_paths": [Case, ...]}`, the latter two capped at `MAX_GENERATED_ITEMS["cases"]`), enforced via `response_json_schema`. Each `Case` carries `path_node_ids`, `path_edge_ids`, `required_assumption_ids`, `supporting_claim_ids`, `contradicting_claim_ids`, `equity_implication_direction`, `estimate_ids`, `quantification_status`, `time_horizon`, `weakening_observation`, `central`, and an optional `broken_reason`.

## Downstream consumer
`select_cases()` does not trust this output as final — it immediately runs `validate_cases(selection, graph, {c.id for c in claims})`, which independently re-derives active nodes/eligible edges/assumptions/estimates from the graph and checks: the central case is actually marked `central=True`; its path IDs exist and are active/eligible; its path edges form a coherent chain; it isn't built entirely from `assumption_only` edges; and every case's (central plus material alternatives — `broken_paths` is not checked at all) claim references fall within the verified claim set. Any violation raises `CaseSelectionError` and aborts the run rather than silently accepting a malformed selection — there is no retry/repair path for a case that fails validation, unlike the graph-patch stages which can loop.
