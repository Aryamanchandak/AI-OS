# `challenge/__init__.py`

This module runs the "attack the graph" stage of the pipeline: three separate LLM calls, backed by the three sibling `.md` prompts, that either propose objections to the causal graph, holistically clean it up, or rule on the objections and turn accepted ones into an applied `GraphPatch`.

## Main entry points

### `whole_graph_review(run_id, graph, claims, model) -> GraphPatch`
Calls `model.generate(..., prompt_name="challenge/whole_graph_reviewer.md", schema=GraphPatch, model_tier="reasoning")` with the full graph and claim list serialized to JSON. This is the odd one out: it skips the finding/decision cycle entirely and asks the model to return a `GraphPatch` directly. The caller (`pipeline/__init__.py`) is responsible for applying the patch — this function itself never calls `apply_patch`. In the pipeline it runs once, after quantification and before `challenge`/`adjudicate`, with `apply_patch(..., require_indian_path=True)` applied by the caller only if `review_patch.operations` is non-empty.

### `challenge(run_id, graph, claims, failures, model) -> ChallengeResult`
Calls `model.generate(..., prompt_name="challenge/challenger.md", schema=ChallengeResult, model_tier="reasoning")`. The payload adds a third field beyond graph/claims: `research_failures` (the `failures` list, i.e. failed search queries or fetches accumulated during the research stage) — the challenger prompt gets visibility into what research *couldn't* confirm, not just what it did confirm. Returns a `ChallengeResult` — a bare list of `ChallengeFinding` objects (id, target, failure_mode, explanation, severity, claim_ids). Per the prompt (see `challenger.md.explained.md`), the model is explicitly told not to repair the graph itself, only to name specific problems — and the Python code here does nothing but return the raw result, no filtering or validation of the findings.

### `adjudicate(run_id, graph, findings, claims, model, settings) -> tuple[CausalGraph, AdjudicationResult]`
Calls `model.generate(..., prompt_name="challenge/adjudicator.md", schema=AdjudicationResult, model_tier="reasoning")`, feeding it the graph, the `ChallengeResult` from `challenge()`, and the claims. The model returns an `AdjudicationResult` — one `AdjudicationDecision` per finding, each carrying a `decision` enum (`accept_and_revise`, `accept_and_remove`, `accept_and_branch`, `reject_with_reason`, `unresolved`) and an optional `operations` list.

The Python code then does the real work of turning that into a graph change:
```python
operations = [operation for decision in result.decisions if decision.decision.startswith("accept_") for operation in decision.operations]
if not operations: return graph, result
patch = GraphPatch(operations=operations, reason="Accepted challenger findings", evidence_ids=sorted({cid for f in findings.findings for cid in f.claim_ids}))
return apply_patch(graph, patch, settings), result
```
It flattens `.operations` from every decision whose `decision` string starts with `"accept_"` (covers all three accept variants via a prefix check, not an explicit set) and skips `reject_with_reason`/`unresolved` decisions entirely — their reasoning is preserved in the returned `AdjudicationResult` but never touches the graph. If the flattened operations list is empty, the graph is returned unchanged.

**Non-obvious:** `evidence_ids` on the synthesized patch is `sorted({cid for f in findings.findings for cid in f.claim_ids})` — the union of claim IDs across *all* original findings, not just the accepted ones. A finding that was rejected or left unresolved still contributes its claim IDs to the patch's evidence record. This looks intentional-but-loose rather than a bug: it's the same behavior the pipeline module duplicates in its own audit-trail patch construction (`pipeline/__init__.py` lines ~116-117), so it's at least consistent across the codebase, just not scoped as tightly as the name "Accepted challenger findings" implies.

## Which prompt does what (verified against code, not just names)
- `whole_graph_reviewer.md` → `whole_graph_review` — a single holistic pass that emits graph edits directly (`GraphPatch`), no separate finding/ruling step.
- `challenger.md` → `challenge` — the adversarial pass; produces `ChallengeFinding`s only, told not to fix anything itself.
- `adjudicator.md` → `adjudicate` — rules on the challenger's findings, producing per-finding accept/reject decisions with the actual patch operations attached to the accepted ones; Python then applies only the accepted operations via `apply_patch`.

The names accurately describe the roles once you follow the code: challenger proposes, adjudicator rules and supplies edits, whole-graph-reviewer is a separate independent holistic sweep.

## Connects to
- `consequence_radar.config.Settings` — passed through to `apply_patch`.
- `consequence_radar.graph.apply_patch` — used only inside `adjudicate`, to turn the accepted operations into a new `CausalGraph`.
- `consequence_radar.models` — `AdjudicationResult`, `ChallengeResult`, `CausalGraph`, `EvidenceClaim`, `GraphPatch` are the request/response schemas.
- `consequence_radar.providers.model.ModelClient` — the `.generate(...)` protocol all three functions call.
- `consequence_radar.pipeline.__init__` — the sole caller (`from ..challenge import adjudicate, challenge, whole_graph_review`). It runs `whole_graph_review` once (applying its patch itself with `require_indian_path=True`), then `challenge`, then `adjudicate` (which applies its own patch internally), then validates the resulting graph before moving on to `select_cases`.
