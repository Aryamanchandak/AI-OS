# SKILL: extract

You are given the retrieved sources (title, abstract, venue, year, authors,
DOI). For each source, pull out structured evidence. This is a transcription
task with judgement, not a summarization task.

**Copy numbers; do not compute or recall them.** If the abstract says
"n = 24", record 24. If it does not state a sample size, `sample_size` is
`null`. Never infer n from "a small cohort". Never supply an effect size you
remember from elsewhere.

For each source decide its **direction** relative to the sub-claim it was
retrieved for:

- `supports` — the finding is consistent with the sub-claim
- `contradicts` — the finding is inconsistent with it
- `null_result` — the study looked and found no significant effect
- `mixed` — supports on one outcome, contradicts on another
- `irrelevant` — retrieved by the query but does not bear on the sub-claim

`irrelevant` is common and correct. Search engines return noise. Marking a
tangential paper as `supports` to pad the evidence base is the failure mode
this field exists to prevent.

If a source is truncated, paywalled to an abstract stub, or garbled, extract
what is legible, null the rest, and list its id under `unusable_sources`.

## OUTPUT_SCHEMA

```json
{
  "status": "ok | insufficient_input",
  "findings": [
    {
      "source_id": "must match an id from THIS turn's sources",
      "sub_claim_id": "SC1",
      "direction": "supports | contradicts | null_result | mixed | irrelevant",
      "claim_of_paper": "what this paper actually concluded, one sentence",
      "study_design": "RCT | cohort | case-control | cross-sectional | meta-analysis | systematic-review | preprint | in-vitro | animal | unclear",
      "population": "who was studied, or null",
      "sample_size": 0,
      "effect_size": "as stated, e.g. 'd=0.31' — or null",
      "confidence_interval": "as stated — or null",
      "p_value": "as stated — or null",
      "quoted_support": "a short verbatim span from the abstract backing your direction call"
    }
  ],
  "unusable_sources": ["source_id", "..."]
}
```

`quoted_support` must be a literal substring of the source text you were
given. If you cannot find one, the direction is `irrelevant`.
