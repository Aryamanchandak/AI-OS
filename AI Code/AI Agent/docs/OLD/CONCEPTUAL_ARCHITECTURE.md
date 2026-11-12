# AI Agent — Conceptual Architecture (reference)

**Purpose:** the *why* and the mental model behind the loop restructure. This is
the companion to `docs/LOOP_RESTRUCTURE_PLAN.md` (the *how* — named blocks,
functions, contracts). When the technical doc says "do X," this doc says "because
the model works like this." Parked ideas live in `TODO.md`.

**Status:** conceptual layer agreed 2026-07-06.

---

## The shift in one line

The old loop reasons **every step** (Perception runs each iteration), which makes
it a cumbersome ReAct. The new model reasons only at **block boundaries** —
plan a batch of work, execute the whole batch, then think again. Hierarchical,
not step-wise.

**Why this is not ReAct:** ReAct interleaves a reasoning step before every single
action. Here, reasoning happens only when new information can actually change the
plan — at the seam between batches. Execution runs a whole block "heads-down"
before the strategist thinks again.

---

## The three blocks

The run is a loop over three blocks, each owned by one layer:

- **PLAN** — turn the query into a batch of goals.
- **EXECUTE** — ground each goal into an action, run it, produce one result per
  goal.
- **REVIEW** — look at goals vs. results and decide: finished, or here is the
  next batch.

Loop: `PLAN → EXECUTE → REVIEW → (EXECUTE → REVIEW → …) → finished`.

---

## The two roles (sharply split)

- **Perceive — the strategist. No hands.** Never runs a tool, never writes the
  deliverable. It only produces plans (batches of goals) and judgments (finished
  / here's the next batch). Owns PLAN and REVIEW.
- **Decision — the executor and author. The only layer with hands.** It grounds a
  fuzzy goal into a concrete action, runs it (the only layer that touches the
  outside world), and produces every result — including synthesis. This is the
  load-bearing layer; it is deliberately given *more* responsibility, not less.
- **Action — the muscle.** Pure dispatch: takes a grounded tool call, runs it
  against MCP, offloads large outputs to the artifact store. No intelligence.
  Decision *decides*; Action *does*. Keeping it dumb is what makes it reliable.
- **Memory — the record.** Writes down what happened.

Director vs. crew: the strategist decides the scenes and whether a take is good
enough; it cannot act. The executor shoots every scene and delivers the
performance; it does not set the film's direction.

---

## The governing principle: hard rails on safety, freedom on strategy

The system has two contradictory-sounding requirements — "let the machine
decide" and "I must be able to make sense of it." They coexist by splitting on
*kind*:

- **Hard rails (safety) — mechanical, always-on, no LLM judgment.** Never tick a
  goal done unless its output is actually present. Never loop past the cap. Never
  fabricate a tool — if a capability is missing, say so plainly. These are dumb
  and reliable.
- **Freedom (strategy) — the machine genuinely decides.** How to decompose, what
  to batch, how to synthesize, whether output is good enough. No hardcoded
  exceptions. If a result is weak, raise the quality bar — don't carve a special
  case.

Corollary — **no special cases.** The summariser is a tool, run exactly the way
every other tool is run. Synthesis is not a privileged path.

---

## Review is a bounded gap-detector, not an open-ended improver

The danger with a "look at the output and improve it" step is that an LLM will
*always* find an improvement — an infinite polish loop, maximum surface area to
fail. So REVIEW is never handed "the final answer, make it better." It is handed
the goals and the results and runs a **fixed, enumerated checklist**, each item
of which either passes or proposes exactly one concrete follow-up goal
(unaddressed, error, capability-gap, discovery, insufficient, uncovered — see the
technical doc for the live list). The improvement space is real and worth working
through — but as a *named, extensible list of checks*, not free association.

Every finding is logged whether or not it fires, so there is always an audit
trail for *why* another round happened.

---

## Discovery-ordering is solved by timing, not a rule

The classic failure: plan `[list the dir, summarize the papers]`, but the papers
aren't knowable until the listing runs. The fix is not a structural
"independence" rule — it is REVIEW *timing*. PLAN only ever plans what it can
concretely name *now*; it emits the discovery goal and stops. REVIEW runs only
after that output returns, sees the concrete items, and *then* plans the
summaries. The dependent work lands in a later batch for free. (The notion of
"independent goals in a block" matters only for firing tools in parallel, which
is parked — see `TODO.md`.)

---

## Legible logs are a first-class requirement

The operator is not afraid of an autonomous machine — the requirement is to be
able to *make sense* of it. Every block emits a structured, human-legible trace:
the batch of goals and why, each result separately, and the review verdict with
its findings. This trace is also the posterity record of every run, so no
separate goal-persistence store is built.

---

## What is deliberately out (and why)

Parked in `TODO.md`, not cancelled: the research mission (pre-plan context
gathering), parallel tool firing, the round-cap-→-break-to-user design, revisiting
where decomposition lives / how autonomous Decision is, and any efficiency work.
All set aside so the core loop is built correctly first. Things disappear from the
core because they have a reason to — not by fiat.
