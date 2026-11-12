# AI Agent — Loop Restructure (Design + Outcome)

**Status:** ✅ built and statically verified, 2026-07-06. This doc merges what
were previously two companion files — `CONCEPTUAL_ARCHITECTURE.md` (the *why*)
and `LOOP_RESTRUCTURE_PLAN.md` (the *how*) — plus the post-implementation
summary that was appended after the code shipped. Both originals are archived
in `docs/OLD/` with their full inline comment threads intact; nothing here
changes their content, just removes the split.

**Scope:** `src/agent/` only — `schemas.py`, `cognition/perception.py`,
`cognition/decision.py`, `cognition/action.py`, `agent7.py`. No `mcp_server/`.
**Parked items:** see `TODO.md` (research mission, parallel firing,
round-cap-→-user, decomposition-location revisit, efficiency).

Guiding constraints from the operator:
- **Correctness first.** No efficiency/speed work here.
- **Hard rails on safety, freedom on strategy.** (Defined below.)
- **Legible logs are first-class** — the operator must be able to make sense of
  every machine decision.
- **No special cases.** The summariser is a tool, run like every other tool.

---

## Part 1 — Why: the conceptual shift

### The shift in one line

The old loop reasons **every step** (Perception runs each iteration), which
makes it a cumbersome ReAct. The new model reasons only at **block
boundaries** — plan a batch of work, execute the whole batch, then think
again. Hierarchical, not step-wise.

**Why this is not ReAct:** ReAct interleaves a reasoning step before every
single action. Here, reasoning happens only when new information can actually
change the plan — at the seam between batches. Execution runs a whole block
"heads-down" before the strategist thinks again.

### The three blocks

The run is a loop over three blocks, each owned by one layer:

| Block | Owner layer | Job | Touches tools? | Writes deliverable? |
|-------|-------------|-----|----------------|---------------------|
| **PLAN** | `perception.plan` | query → a block of goals | no | no |
| **EXECUTE** | `decision.run_block` → `action.execute` | ground each goal → run it → one result each | **yes** | **yes** |
| **REVIEW** | `perception.review` | check goals vs. results → finished, or next block | no | no |

Loop: `PLAN → EXECUTE → REVIEW → (EXECUTE → REVIEW → …) → finished`.

### The two roles (sharply split)

- **Perceive — the strategist. No hands.** Never runs a tool, never writes the
  deliverable. It only produces plans (batches of goals) and judgments
  (finished / here's the next batch). Owns PLAN and REVIEW.
- **Decision — the executor and author. The only layer with hands.** It
  grounds a fuzzy goal into a concrete action, runs it (the only layer that
  touches the outside world), and produces every result — including
  synthesis. This is the load-bearing layer; it is deliberately given *more*
  responsibility, not less.
- **Action — the muscle.** Pure dispatch: takes a grounded tool call, runs it
  against MCP, offloads large outputs to the artifact store. No intelligence.
  Decision *decides*; Action *does*. Keeping it dumb is what makes it
  reliable.
- **Memory — the record.** Writes down what happened.

Director vs. crew: the strategist decides the scenes and whether a take is
good enough; it cannot act. The executor shoots every scene and delivers the
performance; it does not set the film's direction.

### The governing principle: hard rails on safety, freedom on strategy

The system has two contradictory-sounding requirements — "let the machine
decide" and "I must be able to make sense of it." They coexist by splitting
on *kind*:

- **Hard rails (safety) — mechanical, always-on, no LLM judgment.** Never
  tick a goal done unless its output is actually present. Never loop past the
  cap. Never fabricate a tool — if a capability is missing, say so plainly.
  These are dumb and reliable.
- **Freedom (strategy) — the machine genuinely decides.** How to decompose,
  what to batch, how to synthesize, whether output is good enough. No
  hardcoded exceptions. If a result is weak, raise the quality bar — don't
  carve a special case.

Corollary — **no special cases.** The summariser is a tool, run exactly the
way every other tool is run. Synthesis is not a privileged path.

### Review is a bounded gap-detector, not an open-ended improver

The danger with a "look at the output and improve it" step is that an LLM
will *always* find an improvement — an infinite polish loop, maximum surface
area to fail. So REVIEW is never handed "the final answer, make it better."
It is handed the goals and the results and runs a **fixed, enumerated
checklist**, each item of which either passes or proposes exactly one
concrete follow-up goal (unaddressed, error, capability-gap, discovery,
insufficient, uncovered — see Part 2 §5 for the live list). The improvement
space is real and worth working through — but as a *named, extensible list of
checks*, not free association.

Every finding is logged whether or not it fires, so there is always an audit
trail for *why* another round happened.

### Discovery-ordering is solved by timing, not a rule

The classic failure: plan `[list the dir, summarize the papers]`, but the
papers aren't knowable until the listing runs. The fix is not a structural
"independence" rule — it is REVIEW *timing*. PLAN only ever plans what it can
concretely name *now*; it emits the discovery goal and stops. REVIEW runs
only after that output returns, sees the concrete items, and *then* plans the
summaries. The dependent work lands in a later batch for free. (The notion of
"independent goals in a block" matters only for firing tools in parallel,
which is parked — see `TODO.md`.)

### Legible logs are a first-class requirement

The operator is not afraid of an autonomous machine — the requirement is to
be able to *make sense* of it. Every block emits a structured, human-legible
trace: the batch of goals and why, each result separately, and the review
verdict with its findings. This trace is also the posterity record of every
run, so no separate goal-persistence store is built.

### What is deliberately out (and why)

Parked in `TODO.md`, not cancelled: the research mission (pre-plan context
gathering), parallel tool firing, the round-cap-→-break-to-user design,
revisiting where decomposition lives / how autonomous Decision is, and any
efficiency work. All set aside so the core loop is built correctly first.
Things disappear from the core because they have a reason to — not by fiat.

---

## Part 2 — How: the technical design

### 1. Data contracts (`schemas.py`)

Everything the blocks pass is a typed model. Results are kept **separate** —
never merged — in memory and artifacts.

```python
class Goal:
    id: str
    text: str                         # dense, machine-to-machine imperative intent
    done: bool = False                # set ONLY by rail R1 (output present)
    needs_artifact_ids: list[str] = []  # inputs this goal requires (set by plan/review)

class Block:
    round: int                        # 0 = initial PLAN; 1+ = REVIEW-produced
    goals: list[Goal]
    rationale: str                    # why these goals — logged, auditable

class GoalResult:                     # outcome of ONE goal; never merged with others
    goal_id: str
    kind: Literal["tool", "synthesis", "capability_gap"]
    tool_call: ToolCall | None        # what Decision grounded the goal into
    output_descriptor: str            # short, human-legible, logged
    artifact_id: str | None           # large output offloaded to artifact store
    status: Literal["ok", "error", "capability_gap"]
    message: str = ""                 # capability-gap text / error text

class ReviewFinding:                  # one enumerated reviewer observation
    check: Literal[
        "unaddressed",     # a goal produced no result
        "error",           # a result came back status=error/empty
        "capability_gap",  # Decision flagged a missing tool
        "discovery",       # a result revealed concrete new work (list_dir→papers)
        "insufficient",    # result too thin for what the goal/query demands
        "uncovered",       # combined results miss a part of the original query
    ]
    goal_id: str | None
    detail: str
    proposed_goal_text: str | None    # the follow-up goal, when this finding needs one

class Review:
    finished: bool
    findings: list[ReviewFinding]     # always logged, even when finished
    next_block: Block | None          # built from findings that proposed goals
```

Notes:
- `DecisionOutput` (former single-shot answer/tool) is **replaced** by
  `list[GoalResult]` from `run_block`.
- The final answer is **not** authored by Review. It is the `GoalResult` of
  the synthesis goal (a tool result like any other). The loop composes the
  reply from `GoalResult`s; Review only validates and marks `finished`. This
  is deliberate — Review never gets handed "the answer" and asked to polish
  it.

### 2. Block PLAN — `perception.plan`

```python
def plan(query: str, context: list[MemoryItem]) -> Block
```

- Decompose the query into concrete goals it can specify **right now**.
- **Does not plan work it cannot yet name.** If concrete items are unknown
  until a discovery runs, it emits the discovery goal and stops — REVIEW
  will plan the rest once the discovery output exists.
- Emits `Block(round=0, goals=[...], rationale=...)`.
- No done-tracking, no artifact-attachment guessing, no tickboxes. Strategy
  only.

### 3. Block EXECUTE — `decision.run_block` + `action.execute`

```python
async def run_block(
    block: Block,
    context: list[MemoryItem],
    tools: list[dict],
    session: ClientSession,
) -> list[GoalResult]
```

For each goal in the block (sequentially for now — parallelism parked):
1. **Ground** the goal into an action via one LLM call — either a
   `ToolCall`, or a synthesis tool call (synthesis is a tool, no special
   path).
2. **Run it** through `action.execute` (dispatch + offload big output to
   artifacts).
3. Produce **one `GoalResult`**, kept separate.

Decision is load-bearing: it owns grounding + running + producing every
result, including synthesis. It does **not** invent new goals — new goals
come only from REVIEW.

### 4. Block REVIEW — `perception.review`

```python
def review(
    query: str,
    blocks_so_far: list[Block],
    results_so_far: list[GoalResult],
) -> Review
```

Review is a **bounded gap-detector, not an open-ended improver**. It is
handed the goals and the results (never "the final answer, make it better"),
and runs a fixed, enumerated checklist.

**The reviewer checklist** (each maps to a `ReviewFinding.check`; each either
passes or proposes exactly one follow-up goal):

1. **unaddressed** — every goal has a result? Missing → re-run that goal.
2. **error** — any result `status=error`/empty? → retry or alternative
   approach.
3. **capability_gap** — Decision flagged a missing tool → surface to the
   user; do **not** loop trying to self-fix (rail R3).
4. **discovery** — did a result reveal concrete new work? → propose those
   goals (this is where "appended goals" come from).
5. **insufficient** — is a result too thin for what the goal/query demands?
   → propose a redo with more context.
6. **uncovered** — do the combined results miss a part of the original
   query? → propose a goal for the missing part.

Output: `finished=True` when no check proposes a follow-up; else
`next_block = Block(round=n+1, goals=[proposed goals], rationale=findings)`.
Every finding is logged whether or not it fires. This checklist is **explicit
and extensible**: new checks are added here, deliberately, never inferred at
runtime.

**Context:** REVIEW sees the full run so far (all blocks + all results).
Block boundaries are the right place for full context; more context = better
judgment.

### 5. Hard rails (safety — mechanical, no LLM judgment)

- **R1 — Goal guard.** `goal.done` is set **only** when a real `GoalResult`
  for it is present. A goal can never be ticked done on intent alone.
- **R2 — Caps.** A hard ceiling on rounds and on total steps, so the loop
  always terminates even if REVIEW keeps finding gaps. (Placeholder now; the
  real design is "break back to the user" — `TODO.md` §3.)
- **R3 — No fabricated tools.** If Decision needs a capability not in the
  tool list, it must emit `GoalResult(status="capability_gap", message=...)`
  and never invent a tool or fake an answer.
- **R4 — Repeated-call guard.** If Decision grounds a goal into the exact
  same tool name + arguments already called earlier in the run, the third
  occurrence short-circuits to `GoalResult(status="capability_gap")` instead
  of being run again. Mechanical, no LLM judgment. Carried over from the
  pre-restructure loop.

Everything *not* a rail — how to decompose, what to batch, how to
synthesize, whether output is good enough — is **strategy**, left to the
machine.

### 6. Logging / observability (first-class requirement)

Every run emits a structured, human-legible trace. For each round: the
**Block** (round, goals, rationale), each **GoalResult** separately (goal,
grounded tool call, status, descriptor, artifact id), and the **Review**
(every finding + verdict). This is the spine that lets the operator make
sense of the machine's decisions, and it doubles as the posterity record of
every run (no separate goal-persistence store is built).

### 7. The loop (`agent7.py`) — wiring

```python
context = memory.read(query)                     # (research mission parked — TODO §1)
block   = perception.plan(query, context)
results: list[GoalResult] = []

for round in range(MAX_ROUNDS):                  # R2 cap
    results += await decision.run_block(block, context, tools, session)
    log_round(block, results)
    review = perception.review(query, blocks_so_far, results)
    log_review(review)
    if review.finished:
        return compose_answer(results)           # from synthesis GoalResult(s)
    block = review.next_block

return surface_partial(results)                  # cap hit → (TODO §3: break to user)
```

---

## Part 3 — Post-implementation summary (added 2026-07-06)

This section was added *after* the code described in Parts 1–2 was already
built, so future-you doesn't have to re-read the whole doc cold. Nothing
above was edited or removed — this is purely additive.

**What got built.** The full PLAN → EXECUTE → REVIEW loop as designed:
`perception.plan`, `decision.run_block` (+ `action.execute`),
`perception.review`, wired through `agent7.py`. A static code review against
this doc (2026-07-06) confirmed the three-block loop, the layer split
(Perceive has no hands, Decision is the only layer that touches tools, Action
is pure dispatch), rails R1-R3, the mechanical/LLM split inside REVIEW,
memory re-read every round, and answer composition all match what's
specified above.

**How the three original open decisions actually got resolved.** None of
them came back to the operator for explicit sign-off before the build — the
line-by-line walkthrough that was planned didn't happen before implementation
went ahead.
1. **Synthesis mechanism** → the "internal step, same contract as a tool"
   option was taken. A goal with no tool call becomes
   `GoalResult(kind="synthesis", ...)` carrying the identical
   status/message/done-rule as a tool result. No `summarise` MCP tool was
   added — synthesis stays an internal step, not a real registered tool.
2. **`run_block` return** → confirmed as designed: `list[GoalResult]`, one
   per goal, never merged.
3. **`review` return shape** → confirmed as designed: one `Review` with a
   `finished` discriminant.

**Signatures grew beyond the original spec** (additive, not a contradiction —
needed for things the prose already implied but the original signatures
didn't carry):
- `decision.run_block(...)` also takes `prior_results` and
  `recent_tool_calls` — threads cross-round history into grounding, and
  carries the repeated-call guard (R4) across the *whole run*, not just one
  block.
- `perception.review(...)` also takes an optional `context` — needed so
  REVIEW can route artifacts for the goals it proposes, the same way PLAN
  does.

**A 4th hard rail exists in code that wasn't originally named.** `decision.py`'s
repeated-identical-tool-call guard (3rd identical call → forced
`capability_gap`) predates this restructure and was carried over as-is,
undocumented. It's now named **R4** above so it isn't a silent mechanism.

**One real bug was found in static review, and is now fixed.**
`perception.review()`'s `_ReviewLLMFinding.artifact_indices` — the field the
REVIEW prompt explicitly asks the model to fill in, "same rule as PLAN" — was
parsed off the LLM response but never actually read. Every REVIEW-proposed
goal silently fell back to a keyword-overlap heuristic instead of the model's
explicit routing, unlike PLAN which tries indices first. Fixed in
`perception.py`: LLM-proposed goals (discovery/insufficient/uncovered) now
resolve via those indices first; mechanical retries (unaddressed/error) now
carry forward the *original* goal's own `needs_artifact_ids` instead of
re-guessing from text. The keyword heuristic is now only the last-resort
fallback for both paths.

**Verification status: static only, not live.** Everything above was
confirmed by reading the code, not by running it. A live end-to-end trace has
not been completed — it's blocked by two issues in the sibling `mcp_server`
project (outside this repo, unrelated to this restructure):
- The `memory`/`artifacts` import-path regression (see
  `docs/MEMORY_ARTIFACTS_STATUS.md`, Phase 0) — this is now fixed for the
  memory/artifacts imports specifically.
- A second break: `mcp_server/tools/knowledge_graph` imports a
  `knowledge_graph.kg_store` module that doesn't exist anywhere near
  `mcp_server` — it lives in the unrelated `Database/knowledge-graph`
  project, and `mcp_server.py` never puts it on the path. **Still unresolved**
  as of the memory/artifacts implementation pass — see
  `docs/MEMORY_ARTIFACTS_STATUS.md`.

Both need to be fully resolved before this loop can be run live end-to-end.
See `TODO.md` for the full checklist to verify once that happens.
