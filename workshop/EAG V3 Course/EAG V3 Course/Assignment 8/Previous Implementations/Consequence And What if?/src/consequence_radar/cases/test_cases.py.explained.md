# `cases/test_cases.py`

A narrow smoke test for `validate_cases` — it exercises exactly two of the many rules in that function, not the full rule set.

## What it verifies

`central_case()` is a helper (not a `pytest` fixture) that builds one known-valid `Case` against the shared `graph` fixture from the repo-root `conftest.py`: `N0→N1→N2` nodes, edges `E1` (`N0→N1`, `status="supported"`) and `E2` (`N1→N2`, `status="assumption_only"`), assumption `A1` (`material=True`), estimate `Q1`. The case uses `path_edge_ids=["E1","E2"]`, `path_node_ids=["N0","N1","N2"]`, `required_assumption_ids=["A1"]`, `supporting_claim_ids=["C1"]`, `estimate_ids=["Q1"]`, `quantification_status="directional_only"`, and `central=True`.

`test_central_case_and_alternative_rules(graph)`:
1. Builds `CaseSelection(central_case=central_case())` (no alternatives) and calls `validate_cases(selection, graph)` — **without** a `claim_ids` argument, so it defaults to `None` and the claim-lineage check (`supporting_claim_ids`/`contradicting_claim_ids` subset of verified claims) is skipped entirely for this test. This confirms the baseline case — which references only IDs that genuinely exist in the fixture graph, chains correctly (`E1.dst == "N1" == E2.src`), and isn't entirely `assumption_only` (`E1` is `supported`) — passes without raising.
2. Builds `bad_alt = central_case().model_copy(update={"id":"K2","central":False,"required_assumption_ids":[]})` — a case identical to the valid central case except it's now a non-central alternative with an **empty** `required_assumption_ids`. Wraps it as a `material_alternatives` entry alongside a fresh valid `central_case()`, and asserts `validate_cases` raises `CaseSelectionError`. This is checking the specific rule that a material alternative must be traceable to at least one assumption flagged `material=True`; an alternative with no required assumptions at all fails the `any(...)` check trivially.

## Why it matters
`validate_cases` is the only guard between an LLM's case selection and the report writer, and the module's own inline comment flags that an unchecked claim reference used to slip through and reach the report untouched. This test does not cover that path (claim lineage), nor does it cover missing/inactive nodes or edges, a broken edge chain, an all-`assumption_only` path, or a central case not marked `central=True` — those rules exist in `validate_cases` but have no dedicated test in this file. It only confirms: (a) a well-formed case passes, and (b) the "alternative needs a material assumption" rule actually fires.

## Connects to
- `consequence_radar.cases` — imports `CaseSelectionError`, `validate_cases` (the module under test).
- `consequence_radar.models` — `Case`, `CaseSelection`.
- The root `conftest.py` `graph` fixture — shared across the test suite (also used by other modules' tests), so this test's validity depends on that fixture's exact node/edge/assumption/estimate IDs and statuses staying as described above.
