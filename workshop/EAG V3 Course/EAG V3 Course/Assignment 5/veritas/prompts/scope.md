# SKILL: scope

This is the topic-exploration entry point — the counterpart to `decompose`,
used when the input is an open topic to learn about rather than a specific
claim to check. There is no verdict to reach here, so there is no
falsifier and no P-I-O framing. Your job is to turn a topic into a small
set of genuinely researchable questions.

A good question is specific enough that a literature search against it
would return a bounded, relevant set of papers — "how does creatine affect
the brain" is too broad; "does creatine supplementation affect working
memory under sleep deprivation" is researchable.

At least one question must invite disagreement or open controversy in the
field. A set of questions that are all safely settled produces a bland
essay; a good survey essay tells the reader where the field actually
argues with itself.

If the topic is so broad that no small set of questions could cover it
honestly (e.g. "biology"), set `status` to `too_broad`, narrow it to a
defensible slice yourself, and say so in `notes` — still emit your best
questions so the pipeline can proceed. If the topic is not an empirical
subject at all (pure opinion, a how-to task, fiction), set `status` to
`out_of_scope`.

## OUTPUT_SCHEMA

```json
{
  "status": "ok | too_broad | out_of_scope",
  "normalized_topic": "the topic restated precisely, scoped if you narrowed it",
  "questions": [
    {
      "id": "Q1",
      "text": "one specific, researchable question",
      "priority": "core | supporting"
    }
  ],
  "notes": "one sentence, or empty"
}
```

Emit between 3 and 5 questions. Mark at most 3 as `core` — those are the
ones the essay must actually answer; `supporting` questions can be
addressed more briefly or folded in as context.
