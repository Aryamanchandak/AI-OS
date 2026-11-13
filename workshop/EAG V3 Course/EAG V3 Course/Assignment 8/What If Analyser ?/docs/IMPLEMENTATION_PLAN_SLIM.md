# Releases 2 and 3 — Slim Plan

A companion to `IMPLEMENTATION_PLAN.md`. It replaces §6's Release 2 and
Release 3 only. Everything else in that document — Release 1, §5.1, §5.2, §7's
research design, §12's evaluation plan — stands unchanged.

The original R2 (10 items) and R3 (9 items) add 19 build items and, in the
obvious implementation, roughly **55–70 model calls per analysis**. This plan
delivers the same two claims — *the graph is grounded in retrieved evidence*
and *the graph has been challenged before you see it* — in **8 build items and
11 model calls**.

---

## 1. The reduction rule

The original plan's own review note already found the principle, in the
temporal critic:

> A temporal critic has nowhere to write its conclusion: the `Edge` dataclass
> has no time-lag field, so its findings can only be prose that the adjudicator
> may or may not translate into a sign flip.

Generalise that into a single test applied to every stage in both releases:

> **No AI stage ships unless there is a named schema field for its output to
> land in, and no two stages may write the same field.**

This is not a taste judgement, so it cuts mechanically and the same way every
time. It has three consequences:

1. **The expanded `Edge` becomes item 1 of Release 2, not a Release 4
   dependency.** Nothing downstream can be independent until the schema has
   somewhere for independent opinions to go.
2. **Five critics collapse to one.** Against a representation of ±1 signs and
   three strength buckets there are not five distinct fields to disagree in.
   Critics that would write to the same field are the same critic.
   To be precise about what this changes: §7.6 already runs one critic in Quick
   mode, so the cut is to **build scope and Deep mode** — §6 requires *building*
   five critic stages and Deep *runs* all five. This plan builds one stage with
   a selectable role.
3. **Stages whose only consumer is the next prompt get deleted, not shrunk.**
   A summarisation stage that writes no field and is read by exactly one
   downstream prompt is a prompt fragment, not a pipeline stage.

Two corollaries that account for most of the call-count reduction:

- **Per-item stages must batch.** Any stage phrased "for each source" or "for
  each edge" is an unbounded call count wearing a fixed-cost disguise. Batch M
  items per call, or select the subset that matters.
- **Replacement is not addition.** "Research-aware graph extraction" and
  "candidate graph builder" both *replace* the existing `extract_graph` call.
  Counting them as new stages double-counts the pipeline's single most
  expensive call.

---

## 2. Release 2 (slim) — "Grounded Enough"

**Goal:** the graph is built from retrieved evidence, and the UI can tell a
sourced fact from a model assumption. Nothing more.

| # | Item | LLM calls | Writes to |
|---|---|:---:|---|
| 1 | Expanded `Edge` + `SourceRecord` + `EvidenceClaim` schemas | 0 | — (enables everything below) |
| 2 | Research planner → `ResearchPlan` | 1 | `ResearchPlan.query_groups` |
| 3 | One search provider + fetch + clean-text extraction | 0 LLM | `SourceRecord.*` |
| 4 | Deterministic dedup and source ranking | 0 | `SourceRecord.authority/recency/relevance` |
| 5 | **Batched** claim extraction (10 sources per call) | 2 | `EvidenceClaim[]` |
| 6 | Research-aware extraction (**replaces** today's call) | 0 net | `Edge.evidence_status`, `Edge.supporting_claim_ids` |
| 7 | Source cards + fact/forecast/inference/assumption badges | 0 | — (renders §1 fields) |
| 8 | Research failure → degrade to today's ungrounded path | 0 | — |

**Net new LLM calls: 3.**

### What was cut, and where it went

| Original R2 item | Disposition |
|---|---|
| Source deduplication and *ranking* (AI) | **Kept, made deterministic.** Authority, recency and relevance are lookup tables and date arithmetic, not judgement. §7.4's eight-axis scoring is a Release 4 refinement. |
| Claim extraction (per source) | **Kept, batched.** 10 sources per call. This is the single biggest saving in R2: 20 calls → 2. |
| Evidence ledger (as a stage) | **Kept as a data structure, deleted as a stage.** The ledger is what `EvidenceClaim[]` *is* once it is indexed by concept. That is a dict comprehension. |
| Research brief (AI synthesis) | **Cut.** Its only consumer was the graph-builder prompt. Feed the ranked claim list in directly — ~60 claims of ~30 words fits comfortably. Restore it only if the builder's context measurably overflows. |
| Fact/forecast/inference/assumption labels (AI pass) | **Merged into item 5.** The claim extractor already reads the passage; it classifies in the same call. A separate pass re-reads the same text to answer a question it just answered. |
| Deliberate counterevidence retrieval | **Kept — non-negotiable.** It is two extra query groups in the planner's output (§13 lists confirmation bias as a top risk), and it costs zero extra LLM calls because the planner emits them in the one call it already makes. |
| Multi-source retrieval / provider abstraction | **Deferred to R4.** One provider behind a one-method interface. The abstraction is free later; building it now buys nothing. |
| User-uploaded document research | **Deferred to R4.** Ingestion is a different problem (parsing, chunking, size limits) wearing the research release's clothes. |

### Definition of done (unchanged in substance)

- The graph is built from the user brief plus retrieved claims.
- Every claim links to a `SourceRecord` and a retrieval timestamp.
- The UI distinguishes sourced facts from model assumptions.
- The planner emits counterevidence queries.
- Research failure leaves the deterministic analysis intact and says so.

---

## 3. Release 3 (slim) — "One Critic"

**Goal:** the graph you see has survived a structured challenge, and the
load-bearing edges have been checked against evidence.

| # | Item | LLM calls | Writes to |
|---|---|:---:|---|
| 1 | Builder (= R2 item 6, **already counted**) | 0 net | `Graph` |
| 2 | Critic role selection from the brief (deterministic heuristic) | 0 | `critic_role` |
| 3 | One critic, role ∈ {causal, evidence, contrarian} | 1 | `GraphCritique.findings[]` |
| 4 | Adjudicator + graph repair, **capped at one round** | 1 | `Graph`, `AdjudicationReport` |
| 5 | Debate view + graph diff (deterministic set comparison) | 0 | — |
| 6 | Evidence verification of **load-bearing edges only**, batched | 1 | `Edge.evidence_status` |

**Net new LLM calls: 3.**

### The two decisions that make this work

**Critic role is chosen, not stacked.** The original panel — causal, domain,
evidence, temporal, contrarian — has five critics writing findings into one
`GraphCritique`. By the reduction rule they are one stage. Which lens it uses
is picked per run from the brief: a policy question gets the contrarian, a
quantitative one gets the evidence critic, an unfamiliar domain gets the causal
critic. Add a second critic only when an eval shows a specific error class the
first one misses.

**Verification follows C1, not the edge list.** Post-graph verification of
"every important causal edge" is one call per edge — ~20 calls, and the word
"important" is doing unexamined work. But `edge_robustness` in `main.py`
already computes exactly which edges flip an outcome when perturbed. Verify
*those* — typically 3 to 6 — batched into one call. A 20-call stage becomes 1,
and it is justified by the plan's own sensitivity logic rather than by an
arbitrary budget. Edges that change no conclusion are marked `unverified` and
labelled as such, which is more honest than verifying them and implying they
mattered.

### What was cut, and where it went

| Original R3 item | Disposition |
|---|---|
| Domain critic | **Merged** into the critic role menu. |
| Evidence critic | **Merged** into the critic role menu. |
| Contrarian critic | **Merged** into the critic role menu. |
| Temporal critic | **Blocked until `Edge.time_lag` has propagation semantics.** R2 adds the *field*; `propagate.py` still has no notion of time, so a lag value changes no output. Reinstate alongside backlog row 39 (conditional edges and time lags). |
| Multiple builders + adjudicator panel | **Gated on evidence, deferred past R4.** Ship the single reasoning-enabled builder (C3) with one critic, measure it against §12's graph metrics, and only then decide. If one good builder closes the gap, the panel is latency and cost for nothing. |
| Per-edge evidence verification | **Kept, narrowed to load-bearing edges and batched.** |

### Rule 3 check

`Ideas.md` forbids agent loops. Builder → critic → adjudicator is a
straight-line pipeline with a fixed stage count, so it complies. **The cap is
load-bearing:** the moment the adjudicator may send a graph back for another
critique round, this becomes a loop and violates Rule 3. One round, no
send-back, enforced in code rather than in the prompt.

### Definition of done

- Every run produces one structured critique with a named role.
- The adjudicator report lists accepted, changed, and rejected relationships.
- Unresolved disagreements are visible rather than silently resolved.
- Load-bearing edges carry an evidence status; others are explicitly
  `unverified`.
- The debate completes in exactly one round.

---

## 4. API call count

Two readings of "total", both answered.

### 4.1 Per analysis, at runtime

Baseline today, verified in the source: `extract.py:200-217` makes one call and
allows **exactly one** retry; `synth.py:105-125` fires four concurrent calls.
**5 nominal, 6 worst case.**

| Stage | Quick | Deep | Notes |
|---|:---:|:---:|---|
| Research planner | 1 | 1 | |
| Claim extraction (batched) | 2 | 4 | 10 sources/call; ~20 vs ~40 sources |
| Graph builder | 1 | 1 | replaces today's extraction — not additive |
| Critic | 1 | 2 | Deep runs two roles |
| Adjudicator | 1 | 1 | one round, hard cap |
| Edge verification | 1 | 2 | load-bearing edges only, batched |
| Scenario synthesis | 4 | 4 | unchanged from today |
| **Total (nominal)** | **11** | **15** | |
| **Total (every stage retries once)** | **18** | **24** | pathological, not expected |

Separately, and much cheaper — these are HTTP requests, not model calls:

| Non-LLM | Quick | Deep |
|---|:---:|:---:|
| Search-provider queries | ~6 | ~12 |
| Page fetches | ~20 | ~40 |

Keeping these in their own column matters. Merging retrieval into one "API
calls" number is precisely what makes a research release *look* flagrant when
it isn't — 26 near-free HTTP requests and 11 model calls are not the same unit.

**Against the original plan**, compared mode-for-mode. §7.6 already scopes Quick
to one builder and one critic with no edge-by-edge verification, so the fair
Quick comparison is narrower than the headline suggests:

| | Original | Slim | Reduction |
|---|:---:|:---:|:---:|
| Quick mode | ~20–24 | 11 | **~2×** |
| Deep mode | ~75–86 | 15 | **~5×** |

*Original Quick basis:* 1 planner + ~10 per-source claim calls (§7.6 "limited
source count") + 1 research brief + 1 labels pass + 1 builder + 1 critic +
1 adjudicator + 4 synthesis ≈ 20, plus 1 if source ranking is an AI pass.

*Original Deep basis:* 1 planner + ~40 per-source claim calls + 1 brief +
1 labels + 3 builders + 5–15 critiques + 1 adjudicator + ~20 per-edge
verifications + 4 synthesis ≈ 75–86.

Almost all of the saving comes from two changes — batching claim extraction and
verifying only load-bearing edges. Cutting critics barely moves the Quick
number at all; it matters for *quality* (five paraphrases of one objection plus
an adjudicator with the casting vote) and for **build cost**, since the original
requires all five to be written, prompted, and evaluated.

### 4.2 Cumulative, to build and validate both releases

| Phase | Est. LLM calls | Basis |
|---|---:|---|
| Prompt development, 6 new stages | ~200 | ~30 iterations per stage to settle a structured prompt |
| Integration debugging | ~150 | full-pipeline runs during wiring |
| Eval set runs | ~1,200 | 12 situations × 11 calls × 3 repeats (§12 stability metric) × ~3 rounds |
| LLM-judge grading | ~400 | entailment and faithfulness checks on the above |
| **Total** | **~2,000** | order of magnitude, not a quote |

**Cost sketch.** At ~6k input / ~1.5k output tokens per call on
`gemini-2.5-flash`, a slim Quick analysis is roughly 70k in / 17k out. Multiply
by whatever the current Flash rate is — at the ballpark rates in effect when
this was written that lands near **$0.05–0.10 per analysis** and **$10–15 to
build and validate both releases**. Confirm current pricing before quoting
either figure; the token counts are the durable part. Search-provider queries
add roughly $0.005–0.03 per analysis depending on vendor.

The honest headline: **cost is not the binding constraint here — latency and
error-compounding are.** Measure latency as *depth*, not call count: the two
claim-extraction calls are independent and `synth.py` already parallelises its
four via `ThreadPoolExecutor`, so slim Quick is

```
planner → search+fetch → claims(∥) → builder → critic → adjudicator
        → verification → synthesis(∥)
```

**eight hops, ~20–30 seconds.** The original's per-source and per-edge stages
parallelise too, so its penalty is throttling and token spend rather than raw
depth — but every added stage is another chance to produce a confident wrong
answer, and that is the real argument for slimming. It is the argument §13
already makes in its first row.

---

## 5. Build order

Nothing here reorders Release 1 or the §5.2 demo package. Both should ship
first; R2 and R3 assume session state and C1 already exist.

1. **Expanded `Edge` schema** — R2 item 1. Blocks everything.
2. **C3 (thinking budget on extraction)** — one parameter, plus the
   `max_output_tokens` caveat from §5.1. Measure it. It may close enough of the
   gap that R3's critic earns less than expected, which is worth knowing before
   building the critic.
3. **R2 items 2–4** — planner, provider, ranking. Retrieval works before
   anything reasons over it.
4. **R2 items 5–8** — batched claims, research-aware builder, UI, failure path.
   *R2 is shippable here.*
5. **R3 items 2–4** — role selection, one critic, adjudicator.
6. **R3 items 5–6** — debate view, load-bearing verification.

Steps 4 and 6 are both release boundaries: the product is coherent and
demonstrable at each, which the original ordering did not guarantee.

---

## 6. What this plan is betting on

Stated plainly so it can be checked later rather than discovered:

- **That one good critic ≈ five critics against a coarse representation.** If an
  eval shows a distinct error class the single critic misses, add the second
  critic — the role menu is built to take it.
- **That 10 sources per claim-extraction call does not degrade extraction
  quality.** Test at 5, 10 and 20 before fixing the batch size — and note the
  real constraint is **output tokens, not source count**. §7.7 requires storing
  the exact supporting passage, so ten sources' worth of verbatim-bearing claims
  can exceed the `max_output_tokens=8192` ceiling at `extract.py:174`.
  Truncation there produces the same non-retryable `resp.parsed is None` failure
  that §5.1 C3's caveat describes — validation cannot fix an unparseable
  response. Set this stage's output ceiling independently of extraction's, and
  find it empirically.
- **That C1's load-bearing edge set is the right verification target.** It is
  the set that changes conclusions, which is the correct definition of
  "important" — but only if `edge_robustness` is itself trustworthy, and per
  §5.1 C5 it currently perturbs signs in a direction model that ignores edge
  strength. **C5 should be resolved before R3 item 6 ships**, or verification
  will be aimed by a sensitivity calculation the plan has already flagged as
  under-specified.
