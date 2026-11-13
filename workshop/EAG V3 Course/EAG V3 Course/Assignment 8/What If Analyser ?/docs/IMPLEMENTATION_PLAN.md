# What If Analyser — Maximalist AI and UI Implementation Plan

## 1. Purpose

This document turns the current causal-scenario prototype into an implementation
roadmap for an evidence-backed **AI Scenario Strategist**.

The intended product does more than generate a causal graph. It should:

1. Understand the decision behind the user's question.
2. Research current external information.
3. Separate facts, forecasts, assumptions, and AI inferences.
4. Build and critique multiple causal interpretations.
5. Construct decision-relevant scenarios.
6. Calculate their consequences through a transparent engine.
7. Recommend actions and monitoring indicators.
8. Let the user interrogate and modify the analysis conversationally.
9. Refresh the analysis when external conditions change.

This is a maximalist destination, not a proposal to build every feature at once.
The delivery plan deliberately begins with easy, visible improvements, then adds
the external-information and analytical foundations required by the harder
features.

---

## 2. Current Starting Point

The repository already has a useful core:

- One structured AI call extracts an 8–15 node causal graph.
- A deterministic function propagates signs and magnitudes through the graph.
- Four scenarios are generated from two binary unknowns.
- Four AI calls turn resolved outcomes into short narratives.
- Streamlit displays a scenario table, Graphviz diagram, audit tables, traces,
  and edge-sensitivity results.
- The deterministic core has eight passing self-checks.

The main limitations are:

- External information does not inform the graph.
- The AI does not clarify the user's decision, timeframe, or perspective.
- One model produces the graph without an independent critic.
- The fixed two-unknown matrix produces mechanical rather than designed
  scenarios.
- Outcome traces show immediate incoming edges rather than complete causal
  paths.
- AI conclusions cannot be questioned or modified conversationally.
- Evidence, assumptions, confidence, and disagreement are not represented.
- The interface looks like a functional Streamlit prototype rather than a
  premium analyst workspace.
- Completed results are not preserved as a reusable analysis object.

---

## 3. Product Principles

### 3.1 Visible intelligence

The product should make its intelligence legible: clarification, research,
critique, evidence checks, scenario design, and monitoring should be visible
stages with useful intermediate artifacts.

### 3.2 Evidence is part of the model

Citations must not be decorative footnotes. Evidence should attach to claims
and causal edges, including contradictory evidence and limitations.

### 3.3 Preserve deterministic computation

AI should propose structures, assumptions, interpretations, and prose.
Deterministic code should validate graphs, calculate scenario consequences,
compare versions, and measure sensitivity.

### 3.4 Separate concepts that are easy to confuse

The system must represent these independently:

- Direction of effect
- Magnitude of effect
- Confidence in the relationship
- Quality of supporting evidence
- Plausibility of a scenario
- Sensitivity of an outcome

### 3.5 User control

The user must be able to inspect, reject, pin, or change important assumptions.
The system should never silently rebuild an analysis after a conversational
instruction.

### 3.6 Quick mode and Deep mode

The maximalist system should not force every question through the slowest
pipeline:

- **Quick mode:** light research, one builder, one critic, fast scenarios.
- **Deep mode:** broad research, multiple builders, critic panel, adjudication,
  edge verification, and detailed recommendations.

---

## 4. Ranking Method

Improvements are ranked below by **easiness to implement**, as requested.
Impact is scored separately so an easy cosmetic change is not confused with an
easy high-value feature.

### Ease score

| Score | Meaning | Typical scope |
|---|---|---|
| E1 | Very easy | Prompt, formatting, or isolated UI change |
| E2 | Easy | Small feature using existing data and architecture |
| E3 | Moderate | New module or structured AI stage |
| E4 | Hard | Cross-cutting workflow, state, or provider integration |
| E5 | Very hard | New platform capability, monitoring, or advanced simulation |

### Impact score

| Score | Meaning |
|---|---|
| I1 | Minor polish |
| I2 | Helpful |
| I3 | Noticeable product improvement |
| I4 | Major differentiator |
| I5 | Defines the product |

---

## 5. Complete Improvement Backlog Ranked by Easiness

The rank is an implementation-ease rank, not the final build order.

| Rank | Improvement | Workstream | Ease | Impact | Main dependency |
|---:|---|---|:---:|:---:|---|
| 1 | Premium visual theme and typography | UI | E1 | I3 | None |
| 2 | AI-generated names and theses for current four scenarios | AI | E1 | I4 | Existing scenarios |
| 3 | Perspective lenses: investor, operator, policymaker, founder | AI | E1 | I4 | Prompt changes |
| 4 | Generate board brief, investment memo, and risk register formats | AI | E1 | I4 | Existing resolved output |
| 5 | Suggested follow-up questions after every analysis | AI/UI | E1 | I3 | Existing output |
| 6 | Single-call “Challenge this analysis” red-team report | AI | E1 | I4 | Existing graph |
| 7 | Clear badges for AI inference, assumption, and computed result | UI | E1 | I4 | Minimal schema additions |
| 8 | Sidebar analysis brief with timeframe, geography, and perspective | UI | E2 | I4 | Session state |
| 9 | Preserve completed analysis in Streamlit session state | Platform | E2 | I4 | Run-state schema |
| 10 | Branded pipeline progress display | UI | E2 | I3 | Stage events |
| 11 | Scenario cards and improved comparison matrix | UI | E2 | I4 | Existing scenario data |
| 12 | AI clarification interview | AI/UI | E2 | I5 | UserBrief schema |
| 13 | Full intervention-to-outcome causal paths | Core | E2 | I5 | Graph traversal |
| 14 | Richer scenario narratives with winners, losers, triggers, and invalidators | AI | E2 | I4 | Full path context |
| 15 | Select a scenario and inspect one outcome in detail | UI | E2 | I4 | Session state |
| 16 | User-selectable Quick and Deep analysis modes | AI/UI | E2 | I4 | Pipeline configuration |
| 17 | Intelligent scenario architect replacing mechanical labels | AI | E3 | I5 | Scenario schema |
| 18 | Stronger graph validation and structured repair feedback | Core | E3 | I4 | Expanded graph schema |
| 19 | Single external-information research pass | Research | E3 | I5 | Search provider |
| 20 | Source cards with freshness and authority indicators | Research/UI | E3 | I4 | SourceRecord schema |
| 21 | Structured evidence ledger | Research | E3 | I5 | Claim extraction |
| 22 | One builder plus one independent graph critic | AI | E3 | I5 | Critique schema |
| 23 | Complete evaluation harness and representative test set | Evaluation | E3 | I4 | Saved run artifacts |
| 24 | Edge-level confidence, lag, conditions, and evidence status | Core/Research | E3 | I5 | Evidence ledger |
| 25 | User-uploaded document research | Research/UI | E3 | I3 | Document ingestion |
| 26 | Decision strategist: actions, indicators, and reversal signals | AI | E3 | I5 | Final scenarios |
| 27 | Contrarian and black-swan scenario generator | AI | E3 | I4 | Scenario architect |
| 28 | Exact-edge sensitivity explanation instead of aggregate counts | Core/UI | E1 | I4 | None — see §5.1 |
| 29 | Multiple independent graph builders and adjudicator | AI | E4 | I3 | Builder–critic foundation |
| 30 | Post-graph verification of every important causal edge | Research/AI | E4 | I4 | Evidence ledger |
| 31 | Conversational “chat with the analysis” | AI/UI | E4 | I5 | Structured run artifacts |
| 32 | AI-proposed graph edits with user approval and rollback | AI/UI | E4 | I4 | Chat and versioning |
| 33 | Direct visual editing of edges, strengths, and assumptions | UI/Core | E4 | I3 | Stable graph editor state |
| 34 | Research provider abstraction and multi-source retrieval | Research | E4 | I3 | Research pass v1 |
| 35 | Persistent saved analyses and version comparison | Platform/UI | E4 | I4 | Storage layer |
| 36 | Multi-user or collaborative workspaces | Platform | E5 | I2 | Auth and persistence |
| 37 | Monitoring plans and scheduled external refresh | Research/Platform | E5 | I4 | Persistence and scheduler |
| 38 | Material-change detection and scenario reprioritisation | AI/Research | E5 | I4 | Monitoring |
| 39 | Conditional edges, time lags, and feedback approximation | Core | E5 | I3 | New propagation model |
| 40 | Calibrated probability or Monte Carlo layer | Core/Evaluation | E5 | I3 | Quantitative calibration data |

> **Review note (table integrity).** Rows 23–40 were originally written with five
> cells instead of six: the Impact column was missing and the dependency text had
> slid into its place, so `| 23 | … | Evaluation | E3 | Saved run artifacts |`
> rendered as Impact = "Saved run artifacts". The consequence was that §4's
> ranking method — "impact is scored separately so an easy cosmetic change is not
> confused with an easy high-value feature" — silently stopped applying to 45% of
> the backlog. The Impact values above are a reconstruction and should be
> confirmed by the author. Row 28's ease was additionally corrected from E3 to E1
> on the evidence in §5.1.

---

## 5.1 Deterministic-Core Backlog (Review Addition)

The backlog above is almost entirely about adding AI stages, research, and UI.
It contains no item for the deterministic engine that the product's whole claim
of auditability rests on. `propagate.py` implements the Ideas.md Step 3
specification faithfully, but that specification has known simplifications whose
cost is nowhere stated. These items address them.

| Rank | Improvement | Workstream | Ease | Impact | Main dependency |
|---:|---|---|:---:|:---:|---|
| C1 | Exact-edge sensitivity: name the edges, not the count | Core/UI | E1 | I4 | None |
| C2 | Scenario degeneracy check for non-discriminating unknowns | Core | E1 | I4 | None |
| C3 | Restore a thinking budget on the extraction call | AI | E1 | I4 | None |
| C4 | Cache extraction and synthesis by situation string | Platform | E1 | I3 | Session state |
| C5 | Decide explicitly whether edge strength weights the sign vote | Core | E2 | I4 | Test update |
| C6 | Attenuate magnitude by parent magnitude, not hop count alone | Core | E2 | I3 | C5 |
| C7 | Propagate contested/confidence downstream of a contested node | Core | E3 | I3 | C5, C6 |

### C1 — Exact-edge sensitivity

`main.py:edge_robustness` already iterates `for i in range(len(g.edges))` and
knows exactly which edge flip changed which outcome. It discards that
information into `flip_counts[oid] += 1`. Appending `g.edges[i]` to a list
instead of incrementing a counter converts "3 / 24 flips change this" into "this
outcome hangs on the *rupee → import cost* and *import cost → CPI* links" — the
same computation, a materially better answer. This is a few lines, not a new
sensitivity engine, which is why backlog row 28 was re-rated E1.

### C2 — Scenario degeneracy check

`propagate` seeds an unknown's `affects_node_id` and skips that node in the
topological walk. If an unknown lands on a node with no directed path to any
outcome node, that unknown changes nothing an outcome can see, and two of the
four scenarios are numerically identical while the UI still presents them as
distinct worlds. Nothing detects this today. The check is a
`nx.descendants()` call per unknown at extraction-validation time: if the
descendant set contains no outcome node, reject the graph and use the existing
retry nudge.

Note the size of the failure: if `u2` has no outcome descendants then
`(+,+) ≡ (+,-)` *and* `(-,+) ≡ (-,-)`, so the four-world matrix collapses to two
distinct worlds still presented as four. This is a prerequisite for taking the
scenario matrix seriously and it is cheaper than the scenario architect (row 17)
that would otherwise be asked to compensate for it.

### C3 — Thinking budget on extraction

`extract.py` sets `thinking_config=types.ThinkingConfig(thinking_budget=0)` on
the graph-construction call. §8 of this plan states the routing principle "use
the strongest reasoning model for causal construction and adjudication"; the
current code does the opposite on the single call where causal reasoning
actually happens. Synthesis (`synth.py`) can legitimately keep
`thinking_budget=0` — a three-sentence note needs no reasoning budget — but
extraction should not.

**Caveat — this is two parameters, not one.** On Gemini 2.5 thinking tokens draw
against the same output budget as the answer, and `max_output_tokens=8192` was
sized for a 15-node graph JSON and nothing else. Enabling thinking at that
ceiling can truncate a large graph, which makes `resp.parsed` `None` and raises
`ExtractionError("model did not return a parseable causal graph")` — a failure
the retry loop cannot correct, because it is not a validation problem. Raise
`max_output_tokens` alongside the thinking budget and re-test the 15-node case
explicitly.

Subject to that caveat this is the cheapest available quality improvement to the
graph itself, and it should be measured before any builder–critic machinery is
built on top, because a better single builder may close most of the gap that
Release 3 is designed to close.

### C5 — Strength and the sign vote

`propagate` computes `contribution = parent.sign * edge.sign` and sums those ±1
values. `edge.strength` never enters the direction calculation at all — it is
used only to pick a magnitude bucket. Consequently three `low` edges outvote two
`high` edges, and the strengths the extraction prompt works hard to elicit have
no bearing on whether an outcome reads up or down.

This is the behaviour Ideas.md Step 3 specifies, so it is a deliberate
simplification rather than a defect, and no current test pins it — the diamond
fixture in `test_propagate.py` uses all-`high` edges, so weighting would not
change any existing assertion. But the cost is real and unstated: `edge_robustness`
perturbs edge *signs*, so the entire sensitivity story also runs on a direction
model that ignores strength.

Weighting the vote with integer weights (`low=1, med=2, high=3`) does **not**
violate Rule 4 — confidence stays in three buckets and no float appears
anywhere. The decision to make is whether the extra fidelity is worth changing
the resolved output of existing graphs. Either answer is defensible; leaving it
undecided and undocumented is not.

### C6 — Magnitude and parent magnitude

Magnitude is `max(incoming edge strength)` decayed by shortest-path hop distance
from the intervention. Two consequences follow. A node whose parent barely moved
still reports a large magnitude if one incoming edge is strong, because parent
magnitude is not an input. And a node reachable by a short weak path and a long
strong path takes the strong path's strength with the short path's decay,
overstating it. Note that `test_magnitude_decays_across_three_hops` pins the
current hop-based behaviour, so this change has a test cost.

---

## 5.2 Demo-Weight Feature Backlog (Review Addition)

§5.1 hardens the engine. This section does the opposite job: it lists features
chosen for **visible impact per line of code**, for the case where the product
has to sell itself in a five-minute demo before anyone inspects the backbone.

### The asset nobody is using

`propagate()` is a pure function that resolves a full graph in well under a
millisecond — `test_runs_fast` asserts `< 0.01s`. Every scenario re-run is
**free**: no network, no tokens, no latency. The app currently spends that
superpower on rendering four static scenarios once and then throwing the engine
away.

That single fact is the source of almost every item below. Anything that lets
the user *turn a knob and watch the whole model respond instantly* costs nothing
at runtime, cannot fail, cannot hallucinate, and is the most convincing thing
this product can put on a screen. An LLM feature that takes eight seconds and
might be wrong is strictly worse demo material than a deterministic feature that
responds in four milliseconds and is provably right.

**Design rule for this section:** prefer features that re-run propagation over
features that add an LLM call. Reach for a model only where no deterministic
answer exists.

| ID | Feature | Effort | Demo weight | LLM calls | Depends on |
|---|---|:---:|:---:|:---:|---|
| D1 | One-click preset situation gallery | E1 | I5 | 0 | None |
| D2 | Live uncertainty toggles with instant re-resolve | E1 | I5 | 0 | Session state |
| D3 | "This whole analysis hangs on N assumptions" panel | E1 | I5 | 0 | C1 |
| D4 | Consensus strip: how many worlds agree per outcome | E1 | I4 | 0 | None |
| D5 | Counterintuitive-finding detector | E2 | I5 | 0 | None |
| D6 | Time-horizon banding from hop distance | E1 | I4 | 0 | None |
| D7 | Click an outcome, highlight its full causal path | E2 | I5 | 0 | Session state |
| D8 | Scenario A/B diff view | E2 | I4 | 0 | Session state |
| D9 | Mirror world: invert the intervention | E1 | I4 | 0 | None |
| D10 | Live edge-strength and sign overrides | E2 | I5 | 0 | Session state |
| D11 | Animated cascade reveal | E2 | I3 | 0 | None |
| D12 | Conviction score per outcome | E2 | I4 | 0 | C1, D4 |
| D13 | "Nudge the model" re-extraction box | E2 | I4 | 1 | Session state |
| D14 | Download the board brief | E2 | I3 | 0–1 | None |

Note the LLM column: **twelve of fourteen add no model calls at all.** The demo
gets dramatically more impressive without getting slower, more expensive, or
less reliable.

### D1 — Preset situation gallery

Six curated situations as one-click chips under the input box: a rate cut, a
tariff, a supply shock, a regulatory ban, a funding winter, a currency move.

Highest demo-value-to-effort ratio in this entire document. It removes the
thirty seconds of typing that opens every demo, it removes the risk of an
improvised prompt producing a mediocre graph in front of an audience, and —
combined with D2 and C4 caching — it makes the first impressive result appear
about one second after the page loads. Roughly fifteen lines of Streamlit.

Pick the six by actually running them and keeping the ones whose graphs are
clean and whose four worlds genuinely diverge.

### D2 — Live uncertainty toggles

The headline feature. Replace the static four-scenario render with two toggles
bound to `u1` and `u2`, and re-render the causal map from
`propagate(graph, assignment)` on every flip.

The demo line is: *"These are the two things nobody can agree on. Watch what
happens to the entire map when I change my mind about this one."* Nodes recolor,
arrows flip, contested warnings appear and disappear — instantly, with no
spinner, because propagation is pure arithmetic.

The code already has every piece: `all_assignments` builds the assignment dicts,
`propagate` consumes them, `scenario_name` labels them, and `graph_to_dot` draws
them. What is missing is only that results live inside `if run and
situation.strip():` and vanish on the first interaction. This is why session
state is listed as a demo enabler rather than a backbone chore — **D2, D7, D8
and D10 are all impossible until it exists.**

`graph_to_dot` currently styles nodes purely by `node_type` and takes an
unresolved graph. Extend it to accept a resolved graph and tint node fill by
sign and border weight by magnitude, so the map itself carries the scenario
result instead of only the structure.

### D3 — The load-bearing assumptions panel

Once C1 records *which* edges flip an outcome rather than how many, promote it
to a hero panel: **"Change any one of these three links and the conclusion
changes."** Each row names the mechanism sentence the model already wrote.

This reframes the tool from "here is a diagram" to "here is exactly where your
analysis is fragile," which is the thing an analyst will actually pay for. The
computation already runs in `edge_robustness`; this is presentation of data
being discarded today.

### D4 — Consensus strip

For each outcome, count direction agreement across the four resolved graphs and
render one line: **"4 / 4 worlds agree — CPI rises"** versus **"2 / 2 split —
INR is genuinely uncertain."**

A dozen lines of Python over data already in memory, and it is arguably the most
decision-relevant number the product can display: it separates "robust under
uncertainty" from "the answer is a coin flip," which no single scenario view
communicates.

### D5 — Counterintuitive-finding detector

Compute each outcome's naive expectation — the sign along the shortest path from
the intervention — and compare it to the resolved sign. Where they disagree,
surface the outcome as **"Surprising: X falls even though the intervention
pushes it up, because the Y channel dominates."**

This is the most quotable output the system can produce, and it is exactly what
a causal model is *for*: second-order effects that intuition gets wrong. Roughly
thirty lines using `nx.shortest_path` and the existing sign multiplication. The
mechanism sentence for the dominating edge is already stored on `Edge`, so the
explanation writes itself with no model call.

**Fix the tie-break in the spec, not in the code.** Where several shortest paths
of equal length carry different sign products, there is no single naive
expectation, and an implementer left to improvise will pick something arbitrary —
making the flagship "surprising finding" vary between runs on the same graph.
Choose one rule here: take the shortest path whose weakest edge is strongest,
breaking any remaining tie by edge order; if the sign products still disagree,
declare no naive expectation and omit that outcome rather than inventing one.

### D6 — Time-horizon banding

`propagate` already computes `hop`, the shortest-path distance from the
intervention, and uses it only to decay magnitude. Reuse it as a crude clock:
hop 1 = immediate, hop 2 = near-term, hop 3 = downstream.

Group the outcomes under those three headings. It adds an entire temporal
dimension to the output for about twenty lines, using a number the engine
already has. Note that this delivers most of the *perceived* value of the "time
lags" work in backlog row 39 (rated E5) at E1 cost.

Label it honestly as causal distance rather than calendar time **in the rendered
heading itself**, not only in this note. An audience reading "immediate /
near-term / downstream" will hear weeks and months unless the UI says otherwise,
and the graph carries no calendar information at all.

### D7 — Click-to-highlight causal path

Backlog row 13 is the right feature and is rated correctly at E2/I5, but it is
described as a data-layer change. Its value is visual: select an outcome, and
the Graphviz render dims everything except the full set of paths back to the
intervention, with each hop's mechanism sentence listed beside it.

`nx.all_simple_paths(dg, intervention.id, outcome.id)` gives the paths; the
render change is a per-edge `color` and `penwidth` override in `graph_to_dot`.
Watching a fourteen-node tangle collapse to the four links that actually drive
one number is the moment the graph stops looking decorative.

### D8 — Scenario A/B diff

Two dropdowns, two resolved graphs, one list: **"Moving from World A to World D
flips five nodes; here they are, in causal order."**

Pure set comparison over `{n.id: n.sign}` dictionaries. It answers the question
the four-column matrix implies but never states — *what actually differs between
these worlds* — and it makes the two unknowns feel consequential rather than
decorative.

### D9 — Mirror world

`propagate` hardcodes the intervention to `sign = 1`. Parameterise it, run the
whole four-scenario sweep at `-1`, and the user can ask **"and what if the
opposite happens?"** — a rate *hike* instead of a cut — with no new extraction
call, because the causal structure is identical and only the seed changes.

Eight scenarios from one LLM call. Roughly ten lines, and it doubles the
apparent depth of the analysis.

Two points to settle before building. First, inverting the intervention seed
does **not** invert the unknown seeds — `propagate` sets those independently from
the assignment dict — and that is correct: the unknowns are separate
uncertainties, not consequences of the intervention. Say so in the UI, because a
viewer may expect a "mirror" to flip everything. Second, `edge_robustness`
recomputes its own baseline from the assignment it is given, so the sensitivity
panel stays valid against an inverted world — but it will then be reporting on a
scenario the extraction call never considered, which is worth a caption.

### D10 — Live edge overrides

Let the user flip an edge's sign or change its strength in the audit table and
watch the outcomes re-resolve instantly. This is backlog row 33 ("direct visual
editing", rated E4) minus the persistence, versioning, and approval machinery —
which is where all of that row's cost actually sits.

The demo framing is disagreement: *"You don't think a weak rupee feeds through
to inflation that fast? Turn it down and see if my conclusion survives."* It
turns a static artifact into a shared model, which is the single strongest
argument that this is a tool rather than a toy.

Keep it strictly ephemeral for now — an override that resets on re-run needs no
storage layer and no rollback story.

### D11 — Animated cascade reveal

On first render, reveal the graph in topological waves — intervention, then hop
1, then hop 2, then outcomes — with a short delay between frames via `st.empty()`
and successive `graph_to_dot` calls.

Pure eye candy, and it earns its place: it makes causality legible as *movement*
rather than as a static diagram, and it fills the extraction wait with something
better than a spinner. Keep it to roughly 1.5 seconds total and make it skippable.

**Risk — this is the one item that can make the app feel broken.** Streamlit
re-executes the script top-to-bottom on every interaction, and a `time.sleep()`
loop over `st.empty()` blocks the script thread: clicks during the animation
queue instead of responding, and every rerun replays the animation from frame
one. Gate it behind a session-state `has_animated` flag so it plays exactly once
per analysis and never on a rerun. Without that flag the flashiest feature in
this section becomes the most irritating one.

### D12 — Conviction score

Combine D4's cross-scenario agreement with C1's edge-flip fragility into one
0–100 badge per outcome, displayed as a labelled band (`Weak` / `Moderate` /
`Strong`).

Caveat worth respecting: this is the item most likely to read as false
precision, which §13 explicitly warns against and Ideas.md Rule 4 exists to
prevent. Show the band prominently and the number quietly, and put both inputs
in the tooltip so the score is always decomposable back into "3 of 4 worlds
agree, and 2 of 24 edge flips would change it."

### D13 — "Nudge the model" box

One text input after the result: *"You've missed the housing channel."* Re-run
extraction with that line appended to the instruction, then diff the new graph
against the old and highlight what changed.

The only LLM feature in this section, and it earns its slot: it delivers the
*felt* experience of backlog rows 31–32 (conversational analysis, AI-proposed
edits — both E4) for one extra call and no intent classifier, no proposed-change
schema, and no rollback system. The existing `_call_model` `nudge` parameter
already does exactly this for validation retries; it just needs a user-facing
entry point.

Honest limitation to state in the UI: this re-extracts the whole graph rather
than editing it surgically, so unrelated parts of the model may shift. That is
acceptable for a demo and must not be shipped as if it were the copilot.

### D14 — Download the board brief

One button producing a single self-contained HTML page: headline finding, the
consensus strip, four scenario cards, the load-bearing assumptions, and the
causal map as inline SVG (`graphviz` can already emit SVG).

Something the viewer takes away and shows to someone else is worth more than
anything that only exists while the tab is open.

### Suggested demo build order

Roughly a day and a half of work, in this order:

1. Session state — nothing interactive works without it.
2. D1 preset gallery + C4 caching — instant impressive first result.
3. D2 live toggles — the headline moment.
4. C1 → D3 load-bearing assumptions — the credibility moment.
5. D4 consensus strip + D5 counterintuitive finding — the quotable output.
6. D7 path highlighting + D6 time banding — depth.
7. D9 mirror world + D8 diff — breadth.
8. D14 download — the takeaway.

D10, D11, D12 and D13 are the second pass.

### Two backbone items that are really demo risks

Framed for this section rather than §5.1, because both fail *on stage*:

- **Session state (row 9).** Without it the first click after a run wipes the
  screen. There is no version of this demo that survives that.
- **Scenario degeneracy (C2).** If an unknown has no path to any outcome, two of
  the four worlds are identical and the matrix shows duplicate columns. An
  audience member who spots that has found the one flaw that makes the whole
  four-world premise look unserious. One `nx.descendants()` check at validation
  time removes the risk permanently.

Everything else in §5.1 can wait until after the demo. These two cannot.

---

## 6. Recommended Build Order

Ease alone should not determine the sequence. The recommended order combines
ease, impact, architectural dependencies, and visible demonstration value.

### Release 1 — “Gold Layer”

**Goal:** Make the current product look and behave like a substantially more
intelligent analyst without rebuilding the core.

Build:

1. Premium visual system.
2. Structured analysis brief in the sidebar.
3. Session-state preservation.
4. AI clarification interview.
5. AI scenario names and scenario theses.
6. Perspective lenses.
7. Single-call red-team report.
8. Rich scenario cards and comparison matrix.
9. Full causal paths.
10. Decision-oriented narrative sections.
11. Suggested follow-up questions.
12. Multiple executive output formats.

**Definition of done**

- The user is guided from a vague situation to a clear analytical brief.
- Results remain available across Streamlit reruns.
- Four scenarios have distinct names, theses, triggers, and invalidators.
- An outcome can be traced from intervention to result.
- The user can view the analysis from at least four perspectives.
- The UI no longer resembles default Streamlit.

### Release 2 — “Research Grounding”

**Goal:** Introduce a real external-information pass and make evidence visible.

Build:

1. `ResearchPlan` structured output.
2. One search/retrieval provider interface.
3. Source ingestion and clean-text extraction.
4. Source deduplication and ranking.
5. Claim extraction.
6. Evidence ledger.
7. Research brief.
8. Source cards and citations.
9. Fact, forecast, inference, and assumption labels.
10. Research-aware graph extraction.

**Definition of done**

- The graph is built from both the user brief and a stored research brief.
- Every research claim links to a source and retrieval timestamp.
- The UI distinguishes sourced facts from AI assumptions.
- The system deliberately retrieves counterevidence.
- Research failure does not destroy the user's existing analysis.

### Release 3 — “Analyst Debate”

**Goal:** Make the AI challenge and improve its own causal interpretation.

Build:

1. Candidate graph builder.
2. Independent causal critic.
3. Domain critic.
4. Evidence critic.
5. Temporal critic.
6. Contrarian critic.
7. Adjudicator and graph repair.
8. Debate summary and graph diff.
9. Post-graph evidence verification.

**Definition of done**

- Deep mode generates more than one candidate interpretation.
- Every critic returns structured findings.
- The adjudicator explains accepted, changed, and rejected relationships.
- Users can inspect unresolved disagreements.
- Major edges receive an evidence status.

> **Review note (scope Release 3 down).** As written, this release adds six AI
> stages — a candidate builder plus causal, domain, evidence, temporal, and
> contrarian critics, plus an adjudicator — whose entire output space is a graph
> of 8–15 nodes, ±1 edge signs, and three strength buckets. A temporal critic has
> nowhere to write its conclusion: the `Edge` dataclass has no time-lag field, so
> its findings can only be prose that the adjudicator may or may not translate
> into a sign flip. Five critics cannot produce meaningfully distinct structured
> findings against a representation that coarse; they will produce five
> paraphrases of the same objection and an adjudicator with the casting vote.
>
> This is the exact failure mode §13 names in its first row — "more agents create
> more confident errors → intelligence theatre" — applied to this plan's own
> Release 3. Two structural preconditions should gate it:
>
> 1. **Expand the edge schema first.** Row 24 (edge-level confidence, lag,
>    conditions, evidence status) is listed as a *dependent* of the evidence
>    ledger, but it is really a *prerequisite* of the critic panel. A critic can
>    only be independent if it has its own field to disagree in.
> 2. **Establish the single-builder baseline first.** Row 22 (one builder, one
>    critic) plus C3 (thinking budget on extraction) should ship and be measured
>    against the §12 graph metrics before rows 29–30 are built. If a single
>    reasoning-enabled builder with one critic closes most of the quality gap,
>    the multi-builder panel is cost and latency for nothing.
>
> Recommended reduction: ship builder + **one** critic + adjudicator, with the
> critic's role selected per run from {causal, evidence, contrarian} based on the
> brief. Add critics only when an eval shows a specific class of error the
> current critic misses.
>
> **Rule 3 check.** `Ideas.md` lists "no agent loop, no ReAct, no
> LangChain/LlamaIndex/CrewAI" as non-negotiable. A fixed builder → critic →
> adjudicator chain is a straight-line pipeline, not an agent loop, so this
> release does not violate Rule 3 — but the plan should say so explicitly,
> because the moment the adjudicator is allowed to send a graph back for another
> critique round, it does. Cap the debate at one round.

### Release 4 — “Scenario Intelligence”

**Goal:** Replace generic combinations with decision-relevant futures.

Build:

1. Scenario architect.
2. Uncertainty importance ranking.
3. Base, upside, downside, contrarian, policy, and tail-risk templates.
4. Scenario-specific graph overrides.
5. Winners and losers.
6. No-regret and scenario-contingent actions.
7. Monitoring indicators and trigger thresholds.
8. Exact-edge and assumption sensitivity.

**Definition of done**

- Scenarios differ through explicit structured assumptions.
- Each scenario explains why it was selected.
- Recommendations are traceable to scenario outcomes.
- The system identifies which assumptions create the largest divergence.

### Release 5 — “Interactive Analyst”

**Goal:** Turn the completed run into a conversational workspace.

Build:

1. Chat with the analysis.
2. Structured intent classification for chat commands.
3. AI-proposed graph edits.
4. User approval, rejection, and rollback.
5. Direct edge and assumption editing.
6. Analysis versions.
7. Side-by-side comparison.
8. User-document additions after a run.

**Definition of done**

- A natural-language request modifies only the intended artifacts.
- Every change produces a visible before/after diff.
- No modification is applied silently.
- Previous analysis versions can be restored.

### Release 6 — “Living Intelligence”

**Goal:** Keep saved analyses current.

Build:

1. Persistence layer.
2. Monitoring-plan generation.
3. Scheduled retrieval.
4. Material-change classification.
5. Affected-edge detection.
6. Scenario reprioritisation.
7. Notifications and analysis diffs.

**Definition of done**

- New information can update only affected claims, edges, and scenarios.
- The user can see what changed and why.
- Old conclusions remain accessible as versioned history.

---

## 7. External Information Pass — Detailed Design

External research should not be a single “search the web and summarize” prompt.
It should produce reusable, inspectable artifacts.

### 7.1 Research workflow

```text
UserBrief
   ↓
Research Planner
   ↓
Search queries grouped by research objective
   ↓
Retrieval and document ingestion
   ↓
Deduplication and source ranking
   ↓
Claim extraction
   ↓
Supporting and contradictory evidence matching
   ↓
ResearchBrief + EvidenceLedger
   ↓
Causal graph construction
```

### 7.2 Research objectives

The planner should create queries for:

- Current baseline conditions
- Recent material events
- Historical precedents
- Causal mechanisms
- Relevant quantitative indicators
- Regional or sector differences
- Counterarguments
- Evidence that would invalidate the initial framing

### 7.3 Source types

The provider interface should support:

- Government and regulator publications
- Official statistics
- Company filings and investor materials
- Academic research
- Industry reports
- Reputable journalism
- User-provided files
- General web material

### 7.4 Source scoring

Each source should be scored independently on:

- Authority
- Primary versus derivative status
- Relevance
- Recency
- Directness of support
- Independence from other retrieved sources
- Geographic applicability
- Time-horizon applicability

### 7.5 Evidence statuses

| Status | Definition |
|---|---|
| Supported | Strong evidence directly supports the claim |
| Partially supported | Evidence supports only part of the claim |
| Disputed | Credible evidence supports competing interpretations |
| Inferred | AI inference based on related evidence |
| Assumption | Deliberate scenario assumption |
| Unsupported | No satisfactory evidence found |
| Stale | Evidence may no longer reflect current conditions |

### 7.6 Research modes

**Quick mode**

- Small query set
- Limited source count
- One synthesis pass
- One graph builder and one critic

**Deep mode**

- Broader query families
- Primary-source preference
- Explicit counterevidence searches
- Multiple builders and critics
- Edge-by-edge verification

**Private mode**

- User-provided documents only
- No public retrieval
- Same claim and evidence structure

### 7.7 Research quality rules

- Store source URL, title, publisher, publication date, retrieval date, and the
  exact supporting passage.
- Never cite a source merely because it contains the same keywords.
- Do not collapse factual claims and forecasts into one category.
- Retain credible contradictions.
- Mark unsupported graph edges rather than hiding them.
- Allow users to pin, exclude, or replace sources.
- Make research failure recoverable and visible.

---

## 8. AI Pipeline and Contracts

Every AI stage should have a narrow role and return structured output.

| Stage | Input | Output | Model responsibility |
|---|---|---|---|
| Intent analyst | Raw user text | `UserBrief` | Clarify decision and context |
| Research planner | `UserBrief` | `ResearchPlan` | Plan evidence gathering |
| Claim extractor | Clean sources | `EvidenceClaim[]` | Convert passages into claims |
| Evidence synthesizer | Claims | `ResearchBrief` | Summarise agreements and disputes |
| Graph builder | Brief + evidence | `CandidateGraph` | Propose causal structure |
| Graph critic | Candidate graph | `GraphCritique` | Find causal weaknesses |
| Adjudicator | Graphs + critiques | `AdjudicationReport` + graph | Resolve disagreements |
| Evidence verifier | Final graph + claims | `EdgeEvidence[]` | Check edge support |
| Scenario architect | Final graph | `ScenarioDefinition[]` | Select meaningful futures |
| Decision strategist | Resolved scenarios | `DecisionBrief` | Recommend actions and indicators |
| Narrative writer | Structured artifacts | Display prose | Explain without changing results |
| Copilot | Analysis + user request | `ProposedChange` | Translate conversation into edits |

### Model-routing principle

- Use fast models for query expansion, extraction, classification, and prose.
- Use the strongest reasoning model for causal construction and adjudication.
- Use deterministic Python for validation, propagation, comparison, and
  sensitivity.
- Cache AI artifacts using their structured inputs.

---

## 9. Proposed Data Models

### `UserBrief`

- Original situation
- Decision to be supported
- Stakeholder perspective
- Geography
- Time horizon
- Desired outcomes
- Constraints
- Research mode

### `SourceRecord`

- Source ID
- URL or document ID
- Title
- Publisher
- Source type
- Publication date
- Retrieval date
- Extracted text
- Authority score
- Recency score
- Relevance score

### `EvidenceClaim`

- Claim ID
- Claim text
- Source ID
- Supporting passage
- Fact, forecast, opinion, or inference
- Geography
- Time horizon
- Confidence
- Concepts referenced

### `EvidenceLink`

- Claim ID
- Graph edge or node ID
- Supports or contradicts
- Direct or indirect support
- Explanation

### Expanded graph edge

- Source node
- Destination node
- Direction
- Strength
- Confidence
- Time lag
- Mechanism
- Conditions
- Evidence status
- Supporting claim IDs
- Contradicting claim IDs

### `ScenarioDefinition`

- Scenario ID
- Name
- Thesis
- Changed assumptions
- Time horizon
- Trigger conditions
- Plausibility band
- Why the scenario was selected

### `DecisionBrief`

- Major outcomes
- Winners and losers
- No-regret actions
- Scenario-specific actions
- Indicators
- Trigger thresholds
- Reversal signals
- Recommendation invalidators

### `AnalysisRun`

- Run ID
- User brief
- Research artifacts
- Candidate graphs
- Critiques
- Final graph
- Scenarios
- Resolved results
- Decision brief
- Monitoring plan
- Versions and timestamps

---

## 10. UI Redesign Plan

### 10.1 Design direction

The interface should feel **precise, refined, and commanding**: closer to a
premium research terminal or strategy desk than a generic dashboard.

Proposed visual direction:

- Deep ink navigation and headings
- Warm ivory main canvas
- Muted stone surfaces
- Burnished gold as the primary accent
- Restrained green and red for directional outcomes
- Fraunces for editorial display headings
- DM Sans for analytical body text and controls
- Generous spacing and strong left alignment
- Subtle reveal transitions for completed pipeline stages

The design should avoid generic blue gradients, glassmorphism, identical card
grids, and excessive decoration.

### 10.2 Information architecture

#### Sidebar

- Situation
- Decision
- Time horizon
- Geography
- Perspective
- Desired outcomes
- Quick or Deep mode
- Research-source controls
- Run analysis

#### Main workspace

1. Analysis status and stage progress
2. Executive scenario summary
3. Scenario comparison matrix
4. Selected scenario details
5. Causal model
6. Evidence and research
7. Red-team findings
8. Actions and indicators
9. Copilot

### 10.3 Primary navigation

Use five main tabs or workspace views:

1. **Brief**
2. **Research**
3. **Causal Model**
4. **Scenarios**
5. **Actions**

The Copilot remains accessible from every post-analysis view.

### 10.4 Key components

#### Analysis brief card

Shows the AI's interpretation of the user's question before expensive work
begins. The user can approve or edit it.

#### Pipeline progress

Shows meaningful stages:

- Understanding the decision
- Planning research
- Gathering evidence
- Building causal models
- Challenging assumptions
- Designing scenarios
- Producing recommendations

#### Scenario hero cards

Each card shows:

- Scenario name
- One-line thesis
- Plausibility band
- Two largest outcome movements
- Dominant trigger
- Primary risk

#### Scenario matrix

Use a styled heatmap-like comparison rather than raw glyphs alone. Preserve
accessible text labels and tooltips.

#### Outcome inspector

When the user selects an outcome:

- Direction and magnitude
- Full causal path
- Competing forces
- Sensitive assumptions
- Supporting and contradictory evidence
- What would invalidate it

#### Causal graph

Add:

- Filters for evidence status and node type
- Scenario overlay
- Selected-path highlighting
- Confidence and lag indicators
- Edge evidence drawer
- Proposed-change diff

#### Evidence ledger

Filter by:

- Supports or contradicts
- Source type
- Recency
- Authority
- Evidence status
- Graph node or edge

#### AI debate view

Shows:

- Critic finding
- Builder response
- Adjudicator decision
- Graph change
- Remaining uncertainty

#### Action board

Separates:

- No-regret actions
- Scenario-contingent actions
- Indicators to watch
- Trigger thresholds
- Reversal signals

### 10.5 Responsive behaviour

- Desktop: sidebar plus wide analytical workspace.
- Tablet: collapsible sidebar and vertically stacked inspectors.
- Mobile: brief, scenarios, and actions first; graph and evidence become
  dedicated drill-down screens.
- Tables must support horizontal scrolling without clipping content.
- Graph rendering must use a mobile-friendly fallback or focused path view.

### 10.6 UI robustness requirements

- Preserve run state across reruns.
- Provide loading, partial-success, empty, and failure states for every external
  operation.
- Do not hide deterministic results when a narrative call fails.
- Cache research and model artifacts where safe.
- Keep controls in the sidebar and results in the main workspace.
- Meet WCAG AA contrast for body text.
- Provide visible keyboard focus states.
- Never depend on colour alone to communicate direction or evidence status.

---

## 11. Repository Evolution

The current flat layout is appropriate for the prototype but will become
unmanageable as the pipeline expands.

Proposed structure:

```text
app/
  main.py
  styles.py
  state.py
  pages/
  components/

core/
  models.py
  validation.py
  propagation.py
  sensitivity.py
  paths.py

research/
  planner.py
  retrieval.py
  ingestion.py
  source_ranker.py
  claim_extractor.py
  evidence_ledger.py
  providers/

analysis/
  graph_builder.py
  critics.py
  adjudicator.py
  evidence_verifier.py
  scenario_architect.py
  decision_strategist.py
  copilot.py

orchestration/
  pipeline.py
  events.py
  model_router.py

storage/
  run_repository.py
  source_cache.py

evals/
  datasets/
  graph_eval.py
  evidence_eval.py
  scenario_eval.py
  narrative_eval.py

tests/
```

Migration principles:

- Keep `propagate.py` pure while moving it into `core/`.
- Expand `schema.py` into explicit domain models before adding agents.
- Split prompt responsibilities currently concentrated in `extract.py` and
  `synth.py`.
- Move Streamlit rendering out of the current monolithic `main.py`.
- Introduce orchestration only after individual stage contracts are tested.

---

## 12. Evaluation Plan

More AI stages only improve the product if they improve measurable outputs.

Create an expert-reviewed evaluation set spanning representative domains and
difficult situations.

### Graph metrics

- Valid graph rate
- Duplicate concept rate
- Missing major-variable rate
- Direction agreement with reviewers
- Outcome relevance
- Stability across repeated runs

### Research metrics

- Source quality
- Citation correctness
- Claim-to-source entailment
- Counterevidence recall
- Freshness compliance
- Duplicate-source rate

### Scenario metrics

- Scenario diversity
- Decision relevance
- Explicit assumption differences
- Outcome divergence
- Trigger clarity

### Narrative metrics

- Faithfulness to deterministic results
- Citation faithfulness
- No invented mechanisms
- Recommendation traceability

### Copilot metrics

- Correct intent classification
- Correct artifact selection
- Minimal unintended changes
- Diff accuracy
- Rollback reliability

---

## 13. Key Risks and Controls

| Risk | Consequence | Control |
|---|---|---|
| More agents create more confident errors | Intelligence theatre | Structured artifacts, critics, evaluation |
| Citations do not support claims | False grounding | Store exact passages and run entailment checks |
| Search reinforces the initial framing | Confirmation bias | Mandatory counterevidence queries |
| Deep mode becomes too slow | Poor usability | Quick/Deep modes, concurrency, caching |
| Precise probabilities look authoritative | Misleading analysis | Use plausibility bands until calibrated |
| Chat silently corrupts the graph | Loss of trust | Proposed changes, approval, versioning |
| UI becomes crowded | Cognitive overload | Progressive disclosure and outcome-first views |
| Streamlit limits interaction quality | UI ceiling | Improve in Streamlit first; reassess later |
| Monitoring repeatedly rebuilds everything | High cost and noisy changes | Material-change and affected-artifact detection |

---

## 14. Decisions Required Before Coding

These decisions materially affect the architecture:

1. Primary first user: investor, strategist, founder, policymaker, student, or
   general analyst.
2. Initial domain scope.
3. Default perspective and time horizon.
4. Acceptable external source types.
5. Whether user-uploaded documents are required early.
6. Quick mode and Deep mode latency targets.
7. Acceptable cost per analysis.
8. Whether analyses must persist between sessions.
9. Whether recommendations should be descriptive or explicitly action-oriented.
10. Whether users should directly edit graphs in the first major release.
11. Whether scenario probabilities are required.
12. What constitutes the flagship demonstration.

---

## 15. Immediate First Work Package

The recommended first implementation package is deliberately visible and
high-impact while remaining compatible with the maximalist architecture.

> **Review note (session state is a hard blocker, not an item).** Backlog row 9
> is rated E2/I4 and sits ninth, which understates it. `main.py` contains no
> reference to `st.session_state` at all, and every result — matrix, cards,
> graph, audit tables, sensitivity — renders inside `if run and
> situation.strip():`. Streamlit re-executes the file top to bottom on every
> interaction, so the first server-side widget interaction after a run sets `run`
> to `False` and the entire analysis disappears, after five LLM calls. Tabs and
> expanders survive because they are client-side; a selectbox, slider, or chat
> input will not.
>
> That makes session state a prerequisite for rows 8, 11, 15, 16, 31, 32, and 33
> — every interactive feature in the plan. It should be item 1 of the first
> package, before the visual system, and it pairs naturally with C4 (cache
> extraction and synthesis keyed by the situation string) so that a re-run is
> free rather than another five calls.

### Package scope

1. Add `UserBrief` and `AnalysisRun` models.
2. Preserve analysis results in session state.
3. Add sidebar controls for decision, timeframe, geography, perspective, and
   analysis mode.
4. Add one clarification AI pass.
5. Add AI scenario names, theses, triggers, and invalidators.
6. Add one red-team AI pass.
7. Generate complete causal paths.
8. Redesign results into scenario cards, comparison matrix, outcome inspector,
   graph, and challenge view.
9. Add follow-up question suggestions.
10. Add board brief and investment memo outputs.

### Why this package comes first

- It contains mostly E1 and E2 work.
- It produces a large visible improvement.
- It introduces the `UserBrief` and `AnalysisRun` contracts needed by research,
  chat, persistence, and monitoring.
- It does not prematurely commit to a particular search provider.
- It preserves the deterministic propagation engine.

### Exit criteria

- A user can turn an ambiguous statement into an approved structured brief.
- The app presents meaningfully named scenarios rather than mechanical toggles.
- The user can inspect full causal paths and a contrarian critique.
- Results survive ordinary Streamlit interactions.
- The interface has a cohesive, intentional design system.
- The next research release can consume the saved `UserBrief` without changing
  the user workflow.

---

## 16. Planning Deliverables Before Implementation

Before the first code change, create and approve:

1. `PRODUCT_SPEC.md`
2. `AI_PIPELINE.md`
3. `RESEARCH_ARCHITECTURE.md`
4. `DATA_MODELS.md`
5. `UX_BLUEPRINT.md`
6. `EVALUATION_PLAN.md`

This implementation plan defines the overall roadmap. Those documents will
resolve the open product choices and turn each release into implementable
tickets with exact inputs, outputs, UI states, and acceptance tests.
