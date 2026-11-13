# `challenge/challenger.md`

Five-line system prompt for the adversarial "try to disprove the graph" step — the first of the challenge stage's two sequential prompts (the third, `whole_graph_reviewer.md`, runs as an independent pass rather than part of this sequence).

## Role in the pipeline
Consumed by `challenge()` in `challenge/__init__.py`, called once per pipeline run after `whole_graph_review`'s patch has been applied. Its job is purely destructive/critical: the prompt opens with "Try deliberately to disprove this complete Indian-equity hypothesis" and closes with "Do not repair the graph and do not invent sources, numbers, or probabilities" — it is explicitly forbidden from proposing fixes, only naming problems. Fixing is `adjudicator.md`'s job, one step later.

## Expected inputs
`challenge()` sends JSON with three keys:
- `graph` — full `CausalGraph`.
- `claims` — list of `EvidenceClaim`.
- `research_failures` — the `failures: list[str]` accumulated during the research loop (failed search queries, failed fetches), giving the challenger visibility into what evidence-gathering *couldn't* confirm, not just what it did confirm.

The prompt directs the model to test a specific checklist of failure modes: incorrect premise, unsupported mechanism, hidden assumption, confused timing, wrong company/sector, substitution/adaptation effects, regulatory/competitive/currency/behavioural offsets, invalid bases/units/formulas/comparables, existing internal contradictions, and better alternative explanations. It also requires findings to cite only claim IDs actually supplied (no invented citations) and to keep facts/forecasts/assumptions/inferences/estimates classified distinctly — a recurring rule across all the challenge/case/research prompts in this codebase.

## Demanded output format
Structured JSON matching `ChallengeResult` (`{"findings": [ChallengeFinding, ...]}`), enforced via the model client's `response_json_schema`. Each `ChallengeFinding` has `id`, `target_type` (`node`/`edge`/`assumption`/`estimate`), `target_id`, `failure_mode`, `explanation`, `severity` (low/medium/high), and `claim_ids`.

## Downstream consumer
`challenge()` returns the `ChallengeResult` as-is with no filtering — the pipeline saves it as the `"challenge"` artifact and then hands it straight to `adjudicate()` (backed by `adjudicator.md`) as the `findings` input for the ruling step. No code in `challenge/__init__.py` inspects or acts on individual findings before adjudication.
