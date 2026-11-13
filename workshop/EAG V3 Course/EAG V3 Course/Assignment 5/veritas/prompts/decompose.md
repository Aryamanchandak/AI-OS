# SKILL: decompose

Split the claim into atomic sub-claims that can each be checked independently
against published evidence.

A sub-claim is atomic when it contains exactly one asserted relationship
between one population, one intervention/exposure, and one outcome. If a
sub-claim contains "and" joining two outcomes, it is not atomic — split it.

For the claim as a whole, name the **falsifier**: the single concrete finding
that, if it existed in the literature, would refute the claim. A claim with
no possible falsifier is not empirically checkable — set `status` to
`out_of_scope`.

Flag ambiguity rather than resolving it silently. "Creatine improves
cognition" is ambiguous about population (healthy? sleep-deprived? elderly?)
and outcome (working memory? reaction time?). If two readings would send the
search in materially different directions, set `status` to `ambiguous_claim`
and list them under `interpretations` — but still emit your best-guess
sub-claims so the pipeline can proceed.

## OUTPUT_SCHEMA

```json
{
  "status": "ok | ambiguous_claim | out_of_scope",
  "normalized_claim": "the claim restated in P-I-O form",
  "falsifier": "the finding that would refute this claim",
  "interpretations": ["alternative reading", "..."],
  "sub_claims": [
    {
      "id": "SC1",
      "text": "one atomic assertion",
      "population": "who",
      "intervention": "what exposure or treatment",
      "outcome": "what measured effect",
      "priority": "core | supporting"
    }
  ],
  "notes": "one sentence, or empty"
}
```

Emit between 2 and 5 sub-claims. Mark at most 2 as `core` — those are the
ones the verdict actually hinges on.
