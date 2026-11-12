# Steelman Generator — architecture

## The actual problem

Naive LLM steelmanning fails in six predictable ways. Design against these, not for prose quality:

1. **Strawman in a suit** — "some argue X because they value freedom." Rhetorically fine, zero empirical load.
2. **Sycophancy inversion** — steelmans whichever side the prompt leans.
3. **Template collapse** — same five moves regardless of domain.
4. **Unfalsifiable output** — no predictions, so the steelman can never be scored.
5. **Fabricated load-bearing facts** — the argument rests on a number nobody can source.
6. **Charity drift** — reconstructs a position no real advocate holds. Useless for engaging actual opponents.

Core reframe: **a steelman is not a rewrite, it's a world-model reconstruction.** Given claim C, find the strongest coherent world W in which C is correct, then expose W's premises, empirical commitments, predictions, and breaking points.

## Pipeline

**0. Claim surgery** → canonical claim card. Split conflated propositions. Separate empirical claim from value premise from definitional move. Pin scope + time horizon. Reject or force-formalize unfalsifiable mush. Everything downstream keys off this card's hash.

**1. Proponent retrieval** — the single biggest quality lever. Source the steelman to *real named advocates*, not model priors. RBI MPC dissents, BIS/IMF working papers, minority opinions, contra sell-side notes, management rebuttals. Hard rule: if no strong advocate is found, output flags `CONSTRUCTED — no real proponent located` rather than silently inventing one.

**2. Premise excavation** → dependency graph. What must be true for C to hold. Nodes typed `empirical | causal-mechanism | definitional | normative`. This is the layer that separates reconstruction from rhetoric.

**3. Parallel frame agents** — run C through structurally distinct argumentative modes so you don't get one template:
- mechanism/causal
- base rate + historical analog
- political economy / incentives
- asymmetric payoff / option value
- second-order cascade (call [[mirfish]] here — it's the same graph substrate)
- tail-justification ("wrong on average, right where it matters")

Select and merge on strength, not agreement.

**4. Verification pass** — every empirical node hit by retrieval, graded `primary | secondary | contested | unsupported | fabricated`. Load-bearing nodes that come back unsupported force **repair or downgrade** — the argument is not allowed to quietly keep leaning on them. Gaps surface in the output, not in your head.

**5. Red/Blue hardening loop.** Red attacks, Blue repairs without conceding the thesis, k rounds. Use a different model family for Red than Blue — shared blindspots are the failure mode here. Terminate when no new distinct attack survives, or when Blue can only repair by weakening C.

That second termination condition produces the **retreat path**: the ordered sequence of fallback positions under pressure. It's the most useful artifact the system generates and almost nobody builds it.

**6. Dual steelman under budget parity.** Run the full pipeline on ¬C with an *enforced equal budget* — log tokens and searches per side, hard-fail on asymmetry. Judge is blinded: strip provenance, randomize order, no signal about which side the user leans toward.

This step roughly doubles cost and will be the first thing you cut. Cutting it converts the tool into a rationalization engine. Don't.

**7. Crux extraction** — minimal set of nodes where the two steelmen actually diverge. Usually 1–3. Each crux emits: disputed proposition, each side's prediction, the observation that would settle it.

**8. Falsifiable handoff** — predictions with dates and thresholds, written straight into [[decision-tracker]] as pre-registered entries. Calibration scoring later tells you whether steelmanning that position was epistemically justified. This closes the loop across the AI OS and is the reason to build it after the tracker, not before.

**9. Rubric gate** — proponent-sourced? load-bearing claims verified? survived k rounds? cruxes isolated? predictions falsifiable? budget parity logged? Below threshold → regenerate.

## Implementation

- **State = typed argument graph** (JSON, Neo4j-backed). Prose is a *render* of the graph, not the artifact. Re-run the same claim hash in three months and diff which nodes moved — that's a genuinely novel capability.
- **Orchestration**: DAG with fan-out at 3 and 6, loop at 5. Sits in your deliberative layer; frame agents and verification are executive/reactive.
- **Routing**: Haiku for retrieval/extraction, Opus for construction and judging, cross-family for Red.
- **Cache** verification by node hash — you'll re-verify the same macro premises constantly.
- **Mobile render**: graph collapses to a swipeable card stack — claim → cruxes → retreat path → predictions. Full graph desktop-only.

## Domain packs

Rates/macro (reaction functions, curve views). Credit (issuer defense vs short thesis). **Forensic accounting** — highest immediate value: every SA01–SA15 flag gets a mandatory steelman of the benign management explanation before it escalates. That kills your false-positive rate and is a self-contained v0 with a real user.

## Eval

- Ideological Turing test: can a real proponent (or a model conditioned as one) tell the output wasn't written by a believer?
- Held-out resolved disputes: does steelmanning the eventually-correct minority position score high *at the time*?
- Long-run: calibration curve from the decision tracker.

## Phasing

v0 claim card + premise graph + verification, single side, forensic-accounting pack → v1 Red/Blue loop → v2 dual steelman + crux extraction → v3 tracker integration.

Given the note about designing to 70% and not shipping: v0 on the forensic pipeline is two days of work and has a user. Build that before the graph substrate tempts you into another architecture month.