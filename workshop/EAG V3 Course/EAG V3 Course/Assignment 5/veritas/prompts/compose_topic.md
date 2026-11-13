# SKILL: compose_topic

Write the essay this pipeline exists to produce, for a reader exploring a
topic out of curiosity, not adjudicating a claim. There is no verdict.
Your job is to leave the reader genuinely understanding the field: what's
established, what's contested, and what's still open.

Do not manufacture a false sense of consensus to make the essay feel more
conclusive than the evidence is. A field with real disagreement is a more
honest and more interesting essay than a flattened one.

## Structure

1. **Open with why this topic matters or is interesting** — give the
   reader a reason to keep reading, not a dictionary definition.
2. **Answer the `core` questions from `scope`** one at a time or woven
   together if they naturally connect — cite findings inline with the
   literal `source_id`, e.g. `(PMID:17046034)`, as you go, the same
   discipline as everywhere else in this pipeline.
3. **Name where the field disagrees** explicitly — which sources point
   different directions, and why that might be (different populations,
   methods, funding, era of research).
4. **Touch the `supporting` questions** more briefly, as context rather
   than full sections.
5. **Close with what's still unsettled** — the genuine open questions a
   curious reader could go dig into next — and a plain-language takeaway.

## Rules

1. Every empirical sentence needs a source_id from `findings`, cited by its
   literal string in parentheses — e.g. `(PMID:17046034)` or
   `(arXiv:2101.00001)`, never a placeholder like "S1". No new facts, no
   source you weren't given, no number not copied from the findings you
   received.
2. If a `core` question has thin or no usable evidence, say so plainly
   inside the essay rather than papering over the gap — "the literature
   on X is thin; the strongest available source is (PMID:17046034), which
   only covers Y" is a good sentence, not a weak one.
3. Target 700–1200 words — topic essays run longer than claim essays
   because there are several questions to answer, not one verdict to
   state. Markdown-lite is fine — `##` section headings, no code fences,
   prose over bullet lists.
4. Same tone as the rest of the pipeline: plain, unhedged where the
   evidence is strong, honestly uncertain where it isn't. Write like a
   good science journalist crossed with the careful research colleague
   from the master prompt's TONE section, not a press release.

## OUTPUT_SCHEMA

```json
{
  "status": "ok",
  "title": "a short, specific essay title",
  "essay": "the full essay, 700-1200 words, markdown-lite, (source_id) citations inline",
  "key_takeaway": "one or two plain-language sentences a reader could repeat to a friend",
  "open_questions": ["a genuinely unresolved question worth the reader's own follow-up", "..."]
}
```
