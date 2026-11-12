# Decision Tracker — Agent Build Spec

**One-sentence objective function:** *Maximise the number of pre-registered, falsifiable decisions per month whose resolution is scored automatically, and drive the gap between declared confidence and realised frequency toward zero.*

Everything below serves that sentence. Anything that doesn't, cut.

---

## Implementation decisions (P0–P7 build)

These choices resolve the open questions for the first build. They are implementation defaults, not claims that later phases are complete.

1. **Session scope:** build P0–P7 in one local-first package. The original two-week phase gates remain the recommended rollout discipline, but are no longer code-delivery gates.
2. **Planning volume:** assume **5 decisions per week** initially. This is a planning baseline and can be configured later; it is not baked into scoring logic.
3. **Decision classes:** model `FORECAST`, `ALLOCATION`, `ANALYTIC`, and `BUILD` from day one. P0 automatically scores binary `FORECAST` records only; the other classes can be resolved manually with their outcome and evidence preserved for later scorers.
4. **Compliance boundary:** `source_classification: blocked` is rejected before persistence, with no event or decision payload stored. This tool is for personal, non-firm, non-MNPI records only. Confirming that its use is permitted remains the user's responsibility and should be done with the relevant compliance function.
5. **Technical baseline:** Python 3.11+, `uv`, Pydantic v2, Typer, and the standard-library SQLite driver. The package is `decision-tracker` and the CLI command is `dt`.
6. **P0 resolution:** `dt resolve` permits explicit manual resolution for all four classes. A `FORECAST` resolution must include a resolver/source so provenance is captured; future phases can restrict auto-resolved forecasts further when resolver adapters exist.
7. **Local storage:** use `.decision-tracker/decision_tracker.db` in the project by default and exclude `.decision-tracker/` from version control so sensitive records are not committed accidentally.
8. **P1 intake:** deterministic one-line/JSON intake remains the safe default. The six-question Interrogator is implemented locally; voice transcription and Telegram delivery are optional adapters activated only when their dependencies and credentials exist. No model may invent a probability.
9. **P2 analytics:** scoring, Wilson intervals, calibration buckets, Murphy decomposition, interval coverage, process/outcome analysis, and weekly/quarterly retrospective payloads are deterministic functions. Segments with fewer than 20 observations and decompositions with fewer than 30 are suppressed.
10. **P3 watcher:** calendar and deterministic local-observation adapters work without credentials. CCIL/NSE/RBI/FBIL and event feeds use a common adapter contract and degrade to human-close alerts when unavailable; they never silently resolve from missing data.
11. **P4 recall:** use a dependency-free local TF-IDF/cosine index over locked reasoning and claims by default. Chroma can replace it later without changing the recall interface.
12. **P5 graph/meta:** build a rebuildable in-memory/JSON graph projection from first-class decision fields. Neo4j export is optional; correlated assumptions and sizing/process patterns work locally.
13. **P6 fan-in:** expose FastMCP tools when `fastmcp` is installed, retain CLI/JSON as the zero-credential fan-in, and provide optional Telegram/voice adapters. External services are disabled until explicitly configured.
14. **P7 dashboard:** ship a read-only Streamlit dashboard with cached local reads, responsive styling, empty/error states, filters, calibration, open-decision, recall, and integrity views.
15. **Non-goals and compliance:** §9 remains in force. The dashboard and integrations cannot mutate decisions, and all ingress paths enforce the same `blocked` source rejection.

---

## 0. The thesis (why most decision journals die)

Three failure modes kill 95% of decision journals. Design against them explicitly:

| Failure | Mechanism | Countermeasure in this spec |
|---|---|---|
| **Capture cost** | Logging takes >60s, so it doesn't happen at the moment of decision | Voice-note / one-line intake; the agent does the structuring, not you (§3.1) |
| **Hindsight leak** | Records get silently edited after the fact; you learn nothing because you were "always right" | Hash-chained append-only log, commit-locked records (§2.4) |
| **No resolution** | 200 open decisions, none scored, no feedback loop | Autonomous Watcher with hard resolution criteria as an admission requirement (§3.3) |

A fourth, specific to markets: **resulting** — judging a decision by its outcome. This system scores *process* and *outcome* on separate axes and lets you regress one on the other.

---

## 1. Scope: what counts as a decision

Four classes, one schema, different resolvers.

| Class | Example | Resolver |
|---|---|---|
| **FORECAST** | "10y IN GS yield closes >6.85% on any day before 30-Sep-26" | Auto (market data) |
| **ALLOCATION** | "Extend duration 0.4y via 7.18% 2033; funded from 1-3y" | Auto (P&L attribution vs. counterfactual) |
| **CREDIT / ANALYTIC** | "Issuer X's receivable days are earnings management; avoid paper >1y" | Semi-auto (event triggers: rating action, default, restatement, promoter pledge) + human close |
| **BUILD / PERSONAL** | "Replace SQLite+NetworkX with Neo4j for the memory substrate" | Human close on a pre-set review date, scored on a pre-set success metric |

**Admission gate.** A record cannot leave `DRAFT` unless it has: (a) a resolution criterion a stranger could evaluate, (b) a resolution date or trigger, (c) a probability or a stated success metric, (d) at least one named falsifier. The Interrogator agent (§3.2) enforces this and is allowed to refuse.

> Rejected: "I think rates go up."
> Accepted: "P=0.65 that the 10y IN GS benchmark (CCIL clean price close) prints ≥6.85% on ≥1 day on or before 2026-09-30. Base rate: 6.85% breached in 4 of the last 11 comparable post-pause windows (~36%). I'm above base rate because of X. Falsifier: an inflation print ≤3.2% before the August MPC."

---

## 2. Data model

### 2.1 The Decision Record

```yaml
id: DR-2026-0412                    # monotonic, immutable
created_at: 2026-08-07T09:14:22+05:30
created_via: voice|chat|mcp|email|cli
author: AC2
class: FORECAST|ALLOCATION|ANALYTIC|BUILD
status: DRAFT|COMMITTED|LIVE|RESOLVED|VOID|SUPERSEDED

title: "10y IN GS ≥6.85% before end-Sep"
domain: [rates, india, gsec]        # controlled vocabulary, feeds retrieval
horizon_days: 54

# --- the claim ---
claim:
  statement: "10y IN GS benchmark closes ≥6.85% on ≥1 day"
  resolution_source: "CCIL clean price close"
  resolution_date: 2026-09-30
  resolution_triggers: []           # optional early-resolve events
  type: binary|categorical|numeric_interval
  probability: 0.65                 # binary
  # or: distribution: {p10: 6.42, p50: 6.71, p90: 7.02}  for numeric

# --- the reasoning at time-of-decision (LOCKED) ---
reasoning:
  base_rate: {value: 0.36, source: "own study, 11 post-pause windows since 2010"}
  drivers: ["fiscal slippage risk", "OMO calendar", "term premium normalisation"]
  key_assumption: "RBI does not resume OMO purchases before September"
  falsifiers: ["CPI ≤3.2% in the July print", "unscheduled OMO purchase announcement"]
  alternatives_considered:
    - {option: "no position", why_rejected: "carry cost of inaction is low but so is optionality"}
    - {option: "express via 5y30y flattener", why_rejected: "curve view is separable, don't conflate"}
  premortem: "It's 30 Sep, yield never traded above 6.72. Most likely because global duration rallied and imported the bid."
  source_refs: [/rr/2026-08-04-mpc-note.md, url:...]

# --- decision vs. forecast linkage ---
action:
  taken: true
  description: "Add 0.4y duration in the 2033"
  size_bps_risk: 12                 # for sizing-vs-confidence consistency check
  counterfactual: "hold cash at 5.90% repo"
  reversibility: LOW|MED|HIGH       # Bezos type-1/type-2
  cost_of_delay: "one week ≈ negligible"

# --- process quality (scored at commit, not at resolution) ---
process:
  base_rate_stated: true
  alternatives_count: 2
  falsifier_named: true
  premortem_done: true
  outside_view_sought: true
  time_of_day: 09:14
  state_flags: [rushed?, post-loss?, consensus-crowded?]
  process_score: 0.86               # computed, §5.3

# --- filled only at resolution (append, never overwrite) ---
resolution:
  resolved_at: null
  outcome: null                     # 1 | 0 | numeric
  evidence: null
  brier: null
  log_score: null
  skill_vs_base_rate: null
  attribution: RIGHT_FOR_RIGHT_REASONS | RIGHT_FOR_WRONG_REASONS |
               WRONG_BUT_SOUND | WRONG_AND_UNSOUND
  failure_tags: []                  # from the taxonomy, §6.2
  lesson: null

integrity:
  commit_hash: sha256(...)
  prev_hash: sha256(...)            # hash chain
  amendments: []                    # each an append-only diff w/ timestamp+reason
```

### 2.2 Storage

- **Event log** — append-only `events` table (SQLite → Postgres when it outgrows one machine). Every state change is an event. The record is a fold over its events. This is what makes hindsight-editing detectable rather than merely discouraged.
- **Projection** — materialised `decisions` view for querying; rebuildable from the log.
- **Vector** — ChromaDB collection over `reasoning.*` blobs, for nearest-neighbour recall (§3.6). Already in your stack.
- **Graph** — Neo4j nodes for `Decision`, `Entity` (issuer, instrument, theme), `Assumption`, `Source`. Edges: `DEPENDS_ON`, `CONTRADICTS`, `SUPERSEDES`, `SHARES_ASSUMPTION_WITH`. This is the piece that pays off later — see §6.3 correlated-bet detection. It also gives your AI OS a concrete first consumer of the unified entity namespace you flagged as the missing substrate.

### 2.3 Why all three stores

Don't build all three in phase 1. But design the schema so the graph is a projection, not a rewrite: keep `domain`, `drivers`, `key_assumption`, and `source_refs` as first-class typed fields from day one so the graph loader is mechanical.

### 2.4 Immutability

On `COMMITTED`, compute `sha256(canonical_json(record))` and chain it to the previous record's hash. Store the chain head in a separate location (a git commit, or a daily line in a plaintext file you back up). Amendments are new events with a mandatory `reason` string; the UI always renders the original alongside. You should be able to prove to a sceptic — including future you — that the 0.65 was written before the outcome.

---

## 3. Agent architecture

Cascade control, mapped to your existing layers. Deliberative on top, reactive at the bottom.

```
                      ┌──────────────────────────────┐
   DELIBERATIVE       │  A6  Retrospective / Meta    │  weekly + quarterly
   (slow, batch)      │      calibration, patterns    │
                      └──────────────┬───────────────┘
                                     │ writes findings
                      ┌──────────────┴───────────────┐
   EXECUTIVE          │  A0  Orchestrator (state m/c) │
   (per-decision)     └──┬────┬────┬────┬────┬────────┘
                         │    │    │    │    │
              ┌──────────┘    │    │    │    └──────────┐
        ┌─────┴─────┐  ┌──────┴──┐ │ ┌──┴────────┐ ┌────┴─────┐
   A1 Intake     A2 Interrogator │ A4 Scorer    A5 Red Team  A6' Recall
   (capture)     (admission gate)│ (math)       (pre-commit) (k-NN prior)
                                  │
                            ┌─────┴──────┐
   REACTIVE                 │ A3 Watcher │  cron / webhook, always on
   (always-on)              └────────────┘
```

### 3.1 A1 — Intake

**Job:** get a decision from your head into `DRAFT` in under 30 seconds, from anywhere.

- Inputs: Telegram/WhatsApp voice note, one-line text, `dt log "..."` CLI, MCP tool call from *any other agent in the AI OS*, forwarded email, highlight from Readwise.
- Transcribe (Whisper local, or Gemma-4-12B for the structuring pass — this is a good local-model job: cheap, high volume, no reasoning depth needed).
- Extract candidate fields; leave everything uncertain as `null`. **Do not hallucinate a probability.** A missing probability is a prompt for A2; a fabricated one is corruption of the dataset.
- Emit `DRAFT`, return a single-line ack with the ID.

**Mobility-first requirement:** intake must work with phone + battery + internet, offline-queued. If it needs the laptop, it will not be used at the moment decisions are actually made.

### 3.2 A2 — Interrogator (the admission gate)

Socratic, adversarial, and *allowed to say no*. Runs as a short async chat thread — asynchronous is the point, so it doesn't block the moment of capture.

Question ladder, stops when the gate clears:
1. How would a stranger with a Bloomberg terminal check this on the resolution date?
2. What's the base rate? If you don't have one — what reference class, and how big?
3. Your number is 0.65. Would you take the other side at 0.55? At 0.75? *(Interval-elicitation to catch anchoring on round numbers. Flag any decision where the indifference band is wider than ±0.15 — that's a "you don't actually have a view" signal.)*
4. Name the single observation that would make you abandon this.
5. What's the second-best option and why isn't it first?
6. Premortem: it's the resolution date and you were wrong. Write the post-mortem now, in one paragraph.

**Design note:** cap at six questions. An interrogator that grinds on will get bypassed, and a bypassed gate is worse than a lenient one. If the gate can't clear in six, park as `DRAFT` and re-prompt tomorrow.

### 3.3 A3 — Watcher

Always-on. Two sub-jobs:

**Resolution.** For each `LIVE` record, evaluate triggers on a cadence set by `horizon_days` (daily for <30d, weekly beyond).
- Market resolvers: CCIL / NSE / RBI DBIE / FBIL pulls. Cache aggressively; these are the only hard external dependencies, so wrap each in an adapter with a stub so the system degrades to human-close rather than breaking.
- Event resolvers: rating actions, exchange filings, MCA, credit events — keyword+entity match against your existing research MCP crawl.
- Calendar resolvers: pure date triggers → ping human.
- On resolution: write `RESOLVED` event, hand to A4.

**Assumption invalidation** (the underrated half). Watch `reasoning.key_assumption` and `falsifiers` on *open* decisions. If a falsifier fires before the resolution date, alert immediately: *"DR-0412's falsifier just triggered — July CPI printed 3.1%. Your call is still live. Update or void?"* This is where a decision tracker stops being a scorekeeper and starts being useful in real time.

### 3.4 A4 — Scorer

Pure function, no LLM. See §5.

### 3.5 A5 — Red Team

Pre-commit only, and *optional per decision* (fire it on high-conviction or large-size records, or on request — running it on everything trains you to ignore it). Given the draft, it retrieves the strongest available counter-case: consensus positioning, the opposing sell-side note, the analogous past decision you got wrong, the crowdedness of the trade. Output is a one-paragraph bear case plus an explicit *"here is the version of you that disagrees"*. It does not block commit. It gets appended to the locked record so you can later check whether you systematically ignore it.

### 3.6 A6' Recall + A6 Retrospective

**Recall (per-decision, synchronous):** at `DRAFT`, k-NN over the vector store + graph traversal for shared assumptions. Returns: *"3 prior decisions share the assumption 'RBI holds OMO'. Two resolved wrong. Your hit rate on RBI-path calls is 5/11 at an average declared confidence of 0.71."* This is the highest-leverage single feature in the system — it puts your track record in front of you *before* you commit, not after.

**Retrospective (batch, weekly/quarterly):** §6.

---

## 4. Lifecycle state machine

```
DRAFT ──(A2 gate passes)──► COMMITTED ──(hash written)──► LIVE
  │                              │                          │
  │                              │                     ┌────┴─────┐
  └──(abandoned, 14d)──► VOID    │                (trigger)   (date)
                                 │                     └────┬─────┘
                        (superseded by new record)          ▼
                                 └────► SUPERSEDED      RESOLVED ──► SCORED
```

Rules worth enforcing in code:
- `LIVE → RESOLVED` cannot be initiated by you for a FORECAST with an auto-resolver. Removes the temptation to close winners early and let losers run past their date.
- `VOID` requires a reason and is itself tracked. A high void rate is a finding, not an escape hatch — if 40% of your calls get voided, you're either overproducing decisions or writing unresolvable ones.
- `SUPERSEDED` keeps both records scored. Changing your mind is fine; erasing that you held the prior view is not.

---

## 5. Scoring

### 5.1 Outcome scoring

**Binary.** Brier score `BS = (p − o)²`, lower is better. Report alongside the log score `LS = −ln(p_assigned_to_realised_outcome)`, which punishes confident errors far harder and is the better teacher for overconfidence. Clip `p` to [0.01, 0.99] so log score stays finite.

**Skill, not raw score.** Raw Brier is meaningless without a reference. Report `SS = 1 − BS/BS_ref` where `BS_ref` is the base rate you declared at commit. Beating your own stated base rate is the actual bar. A 0.18 Brier on a question with a 90% base rate is *bad*.

**Murphy decomposition.** Over any bucket of ≥30 resolved binaries:
`BS = Reliability − Resolution + Uncertainty`
- *Reliability* — calibration error. Fixable by adjusting how you map feeling to number.
- *Resolution* — discrimination, your ability to separate 0.2 events from 0.8 events. This is actual edge and is much harder to improve.
- *Uncertainty* — the irreducible variance of the question set.

The decomposition matters because the two failures need opposite fixes: bad reliability means shade your numbers toward the base rate; bad resolution means your process isn't producing information and shading won't help.

**Numeric/interval.** CRPS for full distributions; for p10/p50/p90 triples, track interval hit rate — over a large sample, ~80% of outcomes should land inside the p10–p90 band. Chronic <80% is the classic overprecision signature and is, empirically, the most common miscalibration among people who are good at directional calls.

**Allocation records.** Score realised P&L against the stated counterfactual, not against zero. Decompose into (direction) × (sizing) × (timing) so you can see which of the three you're actually bad at — most people who "can't trade" are directionally fine and size wrong.

### 5.2 Calibration reporting

- Reliability diagram: declared confidence bucketed [0–10%, 10–20%, …] vs. realised frequency, with Wilson intervals so you don't over-read n=4 buckets.
- Segment by: domain, horizon, decision class, size, time-of-day, and *whether A5 Red Team was run and ignored*.
- Time-decay weight (half-life ~12 months) on the headline number so 2024's calibration doesn't mask this quarter's drift.
- **Minimum-n discipline.** Suppress any segment with n<20. The single fastest way to make this system useless is to let it generate confident narratives from six data points — which is the exact error it exists to correct.

### 5.3 Process score

Independent of outcome. Weighted rubric over `process.*`: base rate stated (0.25), ≥2 alternatives (0.15), falsifier named (0.20), premortem done (0.15), outside view / recall reviewed (0.15), resolution criterion machine-checkable (0.10).

The payoff: once you have ~100 resolved records, regress outcome score on process score. If the slope is flat, either your rubric is wrong or your process theatre isn't doing anything — both worth knowing. If it's positive, you now have a *leading* indicator of decision quality that doesn't require waiting for resolution.

---

## 6. The retrospective layer

### 6.1 Cadence

- **Weekly (5 min, pushed to phone):** what resolved, what's about to resolve, which open decisions have a triggered falsifier, one prompt from the recall engine.
- **Monthly:** calibration deltas, new pattern candidates.
- **Quarterly (the real one):** full decomposition, failure taxonomy roll-up, rubric revision, and a written note by you that gets stored as a record and *scored like everything else*.

### 6.2 Failure taxonomy

Controlled vocabulary — free-text lessons don't aggregate. Tag every wrong-and-unsound resolution with ≥1:

`ANCHORING` · `BASE_RATE_NEGLECT` · `OVERPRECISION` · `CONFIRMATION` · `CONSENSUS_DRIFT` · `RECENCY` · `WRONG_REFERENCE_CLASS` · `MODEL_RIGHT_TIMING_WRONG` · `SIZED_WRONG` · `IGNORED_REDTEAM` · `ASSUMPTION_INVALIDATED_NO_ACTION` · `EXOGENOUS` (genuinely unforecastable — cap this one, it's the ego's favourite)

Track the `EXOGENOUS` rate explicitly. If it exceeds ~15% you are laundering errors.

### 6.3 Pattern detection (what A6 actually looks for)

- Confidence-band miscalibration by domain (*"credit calls well-calibrated; rates calls overconfident above 0.7"*).
- **Correlated bets** — graph query: distinct `LIVE` decisions sharing a `key_assumption` node. Three "independent" positions resting on one RBI assumption is one position with 3× the size, and you will not notice this without the graph.
- Sizing-vs-confidence consistency: regress `size_bps_risk` on `probability`. Non-monotonic is a finding.
- Contextual: time-of-day, post-loss behaviour, decisions made within 24h of a resolved loss.
- Red Team ignore rate vs. outcome delta.
- **Reference-class drift** — are you quietly redefining the base rate to fit the view? Detectable by clustering `reasoning.base_rate.source` strings.

---

## 7. Interfaces

Ranked by how often you'll actually use them.

1. **Telegram/WhatsApp bot** — intake, A2 interrogation thread, weekly push, resolution alerts. This is the product. Everything else is optional.
2. **MCP server** (`decision-tracker-mcp`, FastMCP) — `log_decision`, `commit_decision`, `query_decisions`, `get_calibration`, `resolve`. Exposing this to the rest of the AI OS is the multiplier: your research agent logs a decision when it recommends something; your forensic pipeline logs one when it flags an issuer; every agent in the OS writes to one shared track record. That's the thing you can't buy off the shelf.
3. **CLI** (`dt log`, `dt open`, `dt score`) — desk-side speed.
4. **Read-only web dashboard** — reliability diagrams, open positions, hit rates. Deliberately read-only, deliberately last. A dashboard is the most seductive and least valuable component; building it early is how this project reaches 70% and stops.

---

## 8. Build phases

Each phase ships something you use for two weeks before the next starts. Hard rule.

| Phase | Scope | Ships when |
|---|---|---|
| **P0 — Skeleton** (1 wk) | Pydantic v2 schema, SQLite event log, hash chain, `dt log`/`dt commit`/`dt resolve` CLI, manual scoring. No LLM anywhere. | You've logged 10 real decisions by hand |
| **P1 — Intake + Gate** (1 wk) | Telegram bot, voice→Whisper→Gemma structuring, A2 Interrogator (6-question ladder), async threads | Capture takes <30s on a phone |
| **P2 — Scoring** (1 wk) | A4: Brier, log score, skill score, Murphy decomposition, reliability diagram as a static PNG pushed to Telegram | First 20 resolutions scored automatically |
| **P3 — Watcher** (2 wks) | CCIL/NSE/RBI adapters, falsifier monitoring, resolution alerts, event resolvers via the existing research MCP | Zero manual closes for FORECAST records |
| **P4 — Recall** (1 wk) | ChromaDB over reasoning blobs; prior-decision surfacing at DRAFT | Recall fires on a real decision and changes your number |
| **P5 — Graph + Meta** (2 wks) | Neo4j projection, correlated-bet detection, A6 quarterly retrospective, process-vs-outcome regression | ~100 resolved records exist |
| **P6 — Fan-in** | MCP server; other AI OS agents write decisions | Two other agents are logging |
| **P7 —** *only now* | Web dashboard | — |

**Cold-start reality:** the system produces nothing useful until roughly 50 resolved decisions. At ~5 decisions/week with a 30–60 day mean horizon, that's a four-to-six month runway before the calibration layer says anything trustworthy. Plan for that — and seed it by back-filling 20–30 decisions from your existing published notes and research output, marked `backfilled: true` and **excluded from calibration stats** (you know the outcomes; including them would poison the dataset). Their value is populating the recall index, not scoring you.

---

## 9. Anti-requirements

Explicitly out of scope, to protect the objective function:

- No portfolio management, no order entry, no position keeping. It observes decisions; it doesn't take them.
- No auto-generated decisions. An LLM proposing decisions to score defeats the purpose — you're measuring *your* calibration.
- No social/sharing layer.
- No mobile app. A bot in a messaging app you already have open is strictly better and 100× cheaper.
- No sentiment scoring of your own text. Tempting, unreliable, will produce spurious patterns.

---

## 10. The compliance caveat

You work at an AMC. Two things need a decision *before* P0, and they're constraints on the schema, not afterthoughts:

1. **Keep this personal and clearly separated from firm research records.** A timestamped, hash-chained log of investment views is a discoverable artifact. That's a feature for calibration and a consideration for anything that could be read as a research recommendation under SEBI's research-analyst and internal-code frameworks. Worth a conversation with your compliance desk before it accretes six months of content — much easier to scope now than to retrofit.
2. **Never log MNPI.** Enforce it structurally, not by willpower: a `source_classification` required field (`public` / `internal_non_material` / `blocked`), where `blocked` refuses to persist the body text and stores only the ID and date. The point is that the constraint lives in the schema, so a 30-second voice note at 9pm can't bypass it.

I'm not a lawyer or a compliance officer, and the specifics of your firm's code will govern — but the schema should be built assuming those constraints exist.

---

## 11. Open questions for you

1. **Volume.** Realistically, decisions per week? Under ~3 and the calibration layer never reaches significance, and the design should shift toward the recall engine as the primary value (which is fine, and cheaper to build).
2. **Do ALLOCATION records go in from day one?** They need P&L attribution and a counterfactual engine — meaningfully more work than FORECAST. Deferring them to P5 halves the P0–P3 scope.
3. **Local vs. cloud for the structuring pass.** Gemma-4-12B on the M5 handles intake structuring fine and keeps everything local, which materially simplifies §10. Is that the default, with Claude reserved for A2 and A6 only?
4. **Does the AI OS already have an entity namespace to bind to?** You flagged the shared memory substrate as the critical gap. This project either becomes the forcing function that defines it, or it has to wait — worth deciding deliberately rather than discovering at P5.
