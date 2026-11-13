# `challenge/adjudicator.md`

Five-line system prompt for the "rule on the challenger's objections" step of the pipeline — the third of the three challenge prompts.

## Role in the pipeline
Consumed by `adjudicate()` in `challenge/__init__.py`, which is called once per pipeline run, right after `challenge()` produces a `ChallengeResult`. It is the only prompt in `challenge/` that is authorized to change the graph — the prompt text explicitly says to "return explicit graph operations only for accepted findings," making this the merge point between the challenger's raw objections and an actual `GraphPatch`.

## Expected inputs
`adjudicate()` builds the prompt payload as JSON with three keys:
- `graph` — the full `CausalGraph` (`model_dump(mode="json")`).
- `findings` — the entire `ChallengeResult` from `challenge()` (`model_dump(mode="json")`), i.e. every `ChallengeFinding` the challenger raised.
- `claims` — the list of `EvidenceClaim` objects available for citation.

The prompt text says to "adjudicate each named challenge exactly once" using one of five decisions (`accept_and_revise`, `accept_and_remove`, `accept_and_branch`, `reject_with_reason`, `unresolved`) — implying one `AdjudicationDecision` per input `ChallengeFinding`, though nothing in the Python code enforces that count matches; it's schema-shaped (`AdjudicationResult.decisions`, capped at `MAX_GENERATED_ITEMS["findings"]`) but not cross-checked against `len(findings.findings)`.

It also repeats standing rules seen across all challenge/case prompts: input/source text is untrusted (prompt-injection guard), never invent numbers/sources/claim IDs/probabilities, keep facts vs. forecasts vs. assumptions vs. inferences vs. estimates distinct, and — specific to this prompt — preserve DAG validity and "a concrete Indian-equity transmission path," removing the path outright if evidence defeats it rather than inventing a replacement route.

## Demanded output format
Structured JSON matching `AdjudicationResult` (`{"decisions": [AdjudicationDecision, ...]}`), enforced via `response_json_schema` in `ModelClient.generate` (see `providers/model/__init__.py`). Each `AdjudicationDecision` has `finding_id`, `decision` (one of the five literals above), `reason`, and `operations: list[GraphOperation]` (only meaningful for `accept_*` decisions).

## Downstream consumer
`adjudicate()` in `challenge/__init__.py` parses the result into `AdjudicationResult`, then filters to decisions whose `.decision` starts with `"accept_"`, flattens their `.operations`, wraps them in a `GraphPatch`, and applies it via `consequence_radar.graph.apply_patch`. `reject_with_reason` and `unresolved` decisions are preserved in the returned `AdjudicationResult` (for the pipeline's audit trail / saved artifact) but never reach the graph.
