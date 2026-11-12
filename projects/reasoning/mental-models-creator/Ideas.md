# Model Forge

**The reframe:** a mental model isn't a summary. It's a *compressed causal structure that emits falsifiable predictions*. If it can't predict, it's a taxonomy. That distinction is the whole design.

## The object

Don't output prose. Output a typed record:

```
model:
  name, scope
  boundary_conditions   # where it applies, where it breaks
  entities[]            # nodes
  edges[]               # cause → effect, sign, magnitude, lag
  invariants[]          # what must always hold
  predictions[]         # dated, falsifiable, with confidence
  anomalies[]           # observations it can't explain
  provenance{}          # which source supported which edge
```

Prose is a *rendering* of this. The record is the artifact.

## Ingestion → construction

Input (paper, filing, book chapter, conversation, your own rambling voice note) → extract entities and causal claims → force them into edges with sign/lag → flag every claim you *inferred* vs. the source *stated*. Unsupported edges get marked, not deleted. They're the hypotheses.

## Honing — four adversarial passes

1. **Compression.** Restate in 40 words, then 15. If it doesn't survive, you have notes, not a model.
2. **Prediction extraction.** Force N falsifiable, dated predictions. Zero predictions = reject the model.
3. **Anomaly hunt.** Agent actively searches for counterexamples and asks which edge breaks first. Not "is this right" — "what would have to be true for this to be wrong."
4. **Transfer test.** Apply to an adjacent domain. Generalizes → real structure. Doesn't → you described one dataset.

## The part that makes it worth building

**Model collision.** New model gets checked against your existing library. Two models sharing an entity but claiming opposite causal signs = highest-value alert in the whole system. That's where genuine belief revision happens, and no human does it reliably because you can't hold ten models in working memory at once.

## Why this is the hub, not agent #11

Your stated gap in the AI OS is the missing shared entity namespace. **The model library *is* that namespace, and predictions are the interchange format:**

- Model Forge → builds the belief structure
- Steelman → adversarially hardens a specific edge
- Mirfish → runs models forward on live news
- Decision Tracker → scores the predictions, feeds calibration back to per-model confidence

Model confidence stops being self-reported and becomes *earned* from tracked outcomes.

## Honest flag

This is the fifth agent in the queue and it's architecturally the most ambitious. The 70%-completion pattern will bite hardest here because the design is genuinely fun. **Ship v0 as: markdown record + one honing pass (prediction extraction) + a flat file library.** No Neo4j, no collision detection, no multi-agent. Collision only earns its place once you have ~20 models.

Tell me which part to spec properly and I'll go deep on that one.