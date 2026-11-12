Call it **PRAXIS**. Here's a spec, plus the three places I think your framing is wrong.

## Core object: the principle card, not the book

RAG over book PDFs fails here. It retrieves prose, you need moves. Every book gets destructured into atomic cards:

```yaml
id: recip-003
claim: Concession triggers reciprocal concession (door-in-face)
mechanism: obligation to repay + contrast effect
cues: [negotiation, one-shot-ok, ask-is-refusable, you-move-first]
move: open with a real ask you expect refused, retreat to target
preconditions: initial ask must be plausible, not absurd
failure_mode: absurd anchor reads as bad faith, kills trust
replication: strong (meta-analysed, field-replicated)
source: Cialdini ch.2
```

The `cues` field is the whole product. Situations don't arrive labelled "Kahneman ch.11" — they arrive as "my PM keeps reopening a closed decision." So the index key is **situational features**, not author/topic: `information_asymmetry`, `repeated_game | one_shot`, `status_differential`, `audience_present`, `sunk_cost_live`, `ambiguity_vs_risk`, `who_moves_first`, `reversible | not`. ~20 features, boolean or 3-state. Retrieval = feature-match, then rank.

`replication` is non-negotiable. Half the pop social-psych canon is dead — ego depletion, priming, power posing, most nudge effect sizes post-shrinkage. An agent that confidently hands you a zombie finding in a live negotiation is worse than no agent. Card gets a hard status: `strong / contested / dead / never-tested-outside-lab`. Dead cards stay in the store, flagged, so you stop re-reaching for them.

## The four modes

**LIVE** — you paste a situation, get one move. Not three options.
**STRIP** — pure decision reduction, no theory. Identifies the single load-bearing variable and tells you the rest is noise.
**REP** — the agent generates a synthetic situation targeting a card you've never fired or fired badly. Your situation-builder idea, but *targeted by coverage gap* rather than random.
**AUDIT** — weekly. Coverage map: which cards fired, which never fire, what your hit rate is per card.

## Making it actually ruthless

"Be ruthless" in a system prompt gets you an LLM that says ruthless-sounding things and then hedges. Ruthlessness has to be structural:

- **Output budget.** LIVE mode caps at 120 words. One recommendation. No lists. A word budget kills hedging mechanically because hedges are expensive.
- **Forced discard.** Every output ends with "Ignoring: X, Y" — the things you raised that don't matter. That's the "strip back" you asked for, and it's the part that will annoy you, which is how you know it's working.
- **Underspecification halt.** If the decision-relevant variable is missing, it asks exactly one question and stops. It does not answer around the gap.
- **Lint pass.** Regex/classifier ban on: "it depends", "consider", "you might", "both approaches have merit". Fail → regenerate.
- **NULL is a valid answer.** "No card in your corpus applies. This is execution, not strategy. Go do it." Without this you've built a horoscope generator that always finds a relevant principle.

## The thing that makes it not-astrology

Every LIVE output must carry a **falsifiable prediction**:

> Apply recip-003. Prediction: he counters within 2 days at ≥60% of your opening. If he doesn't, the cue-match was wrong — status differential dominates and reciprocity is masked.

That prediction is the write into your decision-tracker. You don't rebuild scoring here — PRAXIS emits, decision-tracker scores, and the resolved score writes back to the card's hit-rate. Cards with a low hit rate against *your* situations get demoted regardless of literature quality, because the boundary conditions in your life aren't the ones in the paper.

That's the closed loop: read → card → cue-match → prediction → outcome → card weight. Without it you have a chatbot that quotes Cialdini.

## Architecture, mapped to your stack

Deliberative-layer agent. Cards in Neo4j (card nodes, cue nodes, `contradicts` edges between cards — Cialdini's consistency principle and Kahneman on sunk cost will actively disagree, and the agent should surface that instead of picking silently). Verbatim passages in Chroma for grounding, so it can quote the boundary condition rather than paraphrase it. Gateway for inference. Text-in/text-out only — this has to work on a phone at a desk you're not sitting at.

## What I'd actually build first

Not the above. You have a documented pattern of designing to 70% and not shipping, and this spec is exactly the kind of thing that eats four weekends and dies at the Neo4j schema.

**v0, this weekend:** one markdown file, 15 cards, hand-extracted from three books. One system prompt implementing LIVE + STRIP with the word budget and forced-discard. Run it in a chat app on your phone. No graph, no vector store, no gateway.

The 15 cards will tell you within a week whether cue-matching works at all. My guess is your first cue taxonomy is wrong and you'll rewrite it twice — cheap in markdown, expensive in Neo4j. Only build the store once cards exceed ~80 and you can't hold the index in context.

One open question that changes the design: which books? If the corpus is heavy on Cialdini/Thaler/Ariely, the replication filter will delete a painful fraction of it and you should know that before extraction, not after.