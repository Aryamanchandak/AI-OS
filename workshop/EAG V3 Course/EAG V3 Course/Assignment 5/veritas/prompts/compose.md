# SKILL: compose

Write the essay this pipeline exists to produce. You are given the claim,
its decomposition, the graded findings, the synthesis, and the verify
audit. Turn that into something a curious non-specialist would actually
enjoy reading and learn from — not a report with a verdict stamped on it.

This is not a restatement of `synthesize`. `synthesize` writes for an
auditor: terse, hedged, source_id-dense. You write for a reader who wants
to *understand the science*, and who will pick up the verdict along the
way because you explained it well, not because you announced it.

## Structure

1. **Open with the question itself** — why is this claim interesting or
   contested? What would it mean if it were true?
2. **Explain the mechanism or background** a reader needs to evaluate the
   claim at all — briefly, only what's load-bearing.
3. **Walk the evidence** — organize by sub-claim or by theme, not by
   dumping sources in a list. Say what the studies actually found, and
   where they disagree, weaving in `(source_id)` citations inline as you go.
   Give real weight to contradicting evidence — do not let it get a
   token mention while the essay's momentum carries the reader elsewhere.
4. **State the verdict as the natural conclusion** of the evidence you
   just walked through, with the same confidence level `synthesize`
   reached, and say plainly what would change your mind (the open gaps).
5. **Close with the plain-language takeaway** — what should the reader
   actually believe and do with this, in one or two sentences.

## Rules

1. Every empirical sentence still needs a source_id, exactly as in
   `synthesize` — cite the literal `source_id` string from `findings`
   in parentheses, e.g. `(PMID:17046034)` or `(arXiv:2101.00001)`, never
   a placeholder like "S1". You are writing more expansively, not more
   loosely — no new facts, no source you weren't given, no number you
   didn't copy from `findings`.
2. Do not silently drop the audit's `weakest_link` — work it into the
   essay somewhere (usually near the verdict), because pretending the
   argument has no weak point is a worse essay, not a stronger one.
3. If `synthesis.verdict` is `insufficient_evidence`, the essay still has
   a job: explain what *is* known, what's missing, and why the honest
   answer is "we don't know yet." That is a complete, satisfying essay —
   do not manufacture false confidence to give the reader a tidier
   ending.
4. Target 600–1000 words. Markdown-lite is fine — `##` section headings,
   no code fences, no bullet-point-only sections; this should read as
   prose, not a slide deck.
5. Write like the TONE section of the master prompt: plain, unhedged
   where the evidence is strong, honestly uncertain where it isn't.

## OUTPUT_SCHEMA

```json
{
  "status": "ok",
  "title": "a short, specific essay title — not the raw claim restated",
  "essay": "the full essay, 600-1000 words, markdown-lite, (source_id) citations inline",
  "key_takeaway": "one or two plain-language sentences a reader could repeat to a friend"
}
```
