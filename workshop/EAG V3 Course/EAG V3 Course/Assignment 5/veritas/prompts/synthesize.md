# SKILL: synthesize

Weigh the graded findings and reach a verdict on the original claim.

Work sub-claim by sub-claim first, then roll up. A claim is only as strong as
its weakest `core` sub-claim — if SC1 is well supported and SC2 (also core) is
unsupported, the overall verdict cannot be `supported`.

## Verdicts

- `supported` — the weight of evidence favours the claim, contradicting
  evidence is absent or clearly weaker, and at least one high-weight (≥ 2.0)
  source is direct
- `mixed` — meaningful evidence exists on both sides and neither dominates
- `refuted` — the weight of evidence contradicts the claim
- `insufficient_evidence` — too few sources, all low weight, or all indirect.
  **Reach for this verdict readily.** It is the correct answer far more often
  than a confident one, and it is not a failure of the pipeline.

## Confidence

`high` — multiple independent high-weight direct sources agree
`medium` — the direction is clear but rests on few sources or has real caveats
`low` — the verdict is a judgement call, or `ROUND` hit `MAX_ROUNDS`

## Rules

1. Report contradicting evidence explicitly in `contradicting_evidence`, with
   source_ids. Never average a contradiction away into "results are mixed"
   without naming what contradicted what.
2. Every sentence in `verdict_rationale` that asserts something empirical must
   carry a source_id inline, like `(S3)`.
3. Do not introduce a source_id that is not in this turn's graded findings.
4. If `ROUND == MAX_ROUNDS`, you must emit a verdict — set `confidence` to
   `low` and list what remains unresolved in `open_gaps`.

## OUTPUT_SCHEMA

```json
{
  "status": "ok | insufficient_input",
  "verdict": "supported | mixed | refuted | insufficient_evidence",
  "confidence": "high | medium | low",
  "verdict_rationale": "3-6 sentences, each empirical claim carrying (S#)",
  "sub_claim_verdicts": [
    {"sub_claim_id": "SC1", "verdict": "...", "basis": "source_ids and one clause"}
  ],
  "supporting_evidence": [{"source_id": "...", "point": "..."}],
  "contradicting_evidence": [{"source_id": "...", "point": "..."}],
  "open_gaps": ["what evidence would settle this but was not found"],
  "one_line_answer": "the verdict in plain language for a non-specialist"
}
```
