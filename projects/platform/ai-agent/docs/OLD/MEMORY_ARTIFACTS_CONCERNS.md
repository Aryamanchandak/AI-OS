# AI Agent — Memory / Artifacts: Open Concerns (come back to these)

**Status:** 🧭 not-yet-decided design questions. Written 2026-07-08 out of
`docs/MEMORY_ARTIFACTS_DEEPDIVE.md`. These are the things that are **too big,
too philosophical, or too dependent on real usage data** to put in the
implementation plan. Nothing here is a quick fix. Each one is written so you
can pick it up cold in a month and remember exactly why it's open.

**Reviewed 2026-07-08:** a first round of inline comments has been answered
below (marked **Resolved** / **Decided** / **Clarifying note**). Nothing
foundational was removed — only the open questions were converted into
answers, and one new cross-cutting item (Concern 8, auditability) was added
because it surfaced while resolving the rest.

**The distinction that puts an item here vs. in the implementation plan:**
- Implementation plan = bounded, agreed, "do it" → `MEMORY_ARTIFACTS_IMPLEMENTATION_PLAN.md`
- Feature registry = net-new capability, indexed → `TODO.md` §8
- **This doc = a real decision you haven't made yet, with large surface area
  or a dependency on data you don't have.**

BRACKET-COMMENT ANYWHERE. These are the ones you most want to think out loud
on — don't let future-you forget any of them.

---

## Concern 1 — Fact volatility: "true forever" vs. "true for an hour"

**This is the most consequential item in the whole deep-dive.** It surfaced
from three of your own comments independently (§1.6, §2.1, §3.1 in the deep-
dive) all pointing at the same hole.

**The problem in one breath:** `MemoryItem` has no concept of time-bounded
truth. "User's mom's birthday is 15 May" (true indefinitely), "the stock is at
$142" (true for seconds), "it's raining" (true for hours), and "travel plans
for next week" (true for days) are **all written through the same path, stored
identically, embedded identically, and kept forever with zero decay.** Nothing
in `remember()`/`record_outcome()`/`add_fact()` asks "how long should this stay
true," and nothing in `_vector_search()` discounts a hit for being stale.

**Why it's worse than it looks:** a stale fact retrieved with high confidence
actively produces *wrong answers* — it's not just clutter. And it compounds
with Concern 2 (cross-run bleed): an old, confidently-embedded, perishable fact
is exactly the kind of thing an ungated, recency-blind vector search will
happily surface as its "best" match.

**Your instinct (from the deep-dive), which I agree with:** "memory forever" is
fine as a *default* for durable things (preferences, identity facts — pruning
those would be the actual regression). What's missing is **per-item
volatility**, not a blanket shorter lifetime.

> **Resolved:** durability isn't decided by fact *category* [HOW IS THE CATEGORY DECIDED AGAIN ?](e.g. "preference"
> vs. "fact") — it's decided by whether the content has a date attached that
> can pass. See the fuller resolution below (after "why it's a concern");
> in short: identity/relationship facts are durable, dated commitments expire
> at the date, transient state has a short tool-defined half-life.

**The shape I'd propose (NOT a decision — a starting point):**
- One optional field on `MemoryItem`: `expires_at: datetime | None` (or a
  cruder `volatile: bool`). `None` = durable, the current behaviour.
  > **Resolved:** yes, the LLM decides — see the next point.
- `remember()`'s classifier already makes one LLM judgement per item — it can
  set this field on the *same* call, no extra call. ("Is this the kind of fact
  that goes stale? By when?")
  > **Clarifying note:** today `_llm_classify` (`memory.py:329-355`) asks the
  > model for exactly four fields — `kind`, `descriptor`, `keywords`, `value`
  > — in one structured-output call (the `_Classification` model,
  > `memory.py:227-233`). `expires_at` would be a fifth field on that same
  > schema and same call; no new LLM round-trip needed. [YEAH THIS IS FAIR, PRETTY GOOD APPROACH]
- A cheap read-time check: `_vector_search` / `_keyword_search` skip or
  downweight items past `expires_at`. [WHAT IS THIS VECTOR SEARCH, KEYWORD SEARCH ?]
  > **Clarifying note:** two options, not decided which: (a) *hard filter* —
  > drop any item whose `expires_at` is in the past before it's returned from
  > `read()` (`memory.py:203-222`), the same place `kinds` filtering already
  > happens [KINDS AS IN?]; or (b) *soft decay* — keep it in the candidate set but multiply
  > its similarity score down as it ages past `expires_at` (see open
  > sub-question 1 below) [YOU SAY THIS, GIVE ME AN EXAMPLE, AND EXPIRES_AT ? SO WHAT IS ALL THE FIELDS BEING GIVEN BY THE LLM?].

**Why it's a concern and not a plan item:** it touches the write path (classify
+ store), the read path (filter/downweight), the scoring (recency), AND the
schema — three-plus surfaces at once. That's a dedicated design pass, and it
deserves its own sign-off, not a squeeze-in. It's also the item most likely to
interact with the loop (a run that acts on a stale fact is a loop-level
failure, not just a storage one).

> **Resolved — the framing that unlocks this concern:** this isn't a niche
> problem; every personal agent with memory hits it, so it's worth a quick
> look at how existing memory-equipped assistants handle deadline-vs-
> preference decay before building anything bespoke. The reframe that matters
> most: this system is fundamentally a **before-the-fact prep system** — its
> job is to help *before* a deadline or event, not narrate it afterward. That
> turns volatility into two questions, not one: (1) does the fact carry a
> date, and (2) is that date in the future or past *relative to when the
> agent runs* (not when the fact was written). A submission deadline is
> maximally useful the week before and worthless the day after — it should
> expire at the date. A birthday recurs, so it has no expiry-by-date; it's
> durable. A stated preference sits in between: durable by default, but must
> stay *overwritable* — the system needs to update it, not merely decay it,
> when the user's actual behaviour contradicts it. Overwrite-on-contradiction
> is a different mechanism from expiry and isn't designed yet — see new
> sub-question 4 below. [THIS ISSUE SHOULD BE LOOKED AT CREATE A LIST THAT STORES THE MOST IMPORTANT PARTS OF THE SYSTEM THAT I CAN ANALYSE AGAIN AND AGAIN AND IMPORVE OVER TIME]

**Open sub-questions to resolve before building:**
1. Hard expiry (delete/hide past `expires_at`) or soft (decay the score with
   age)? [MAKES SENSE NOW, LETS GO WITH HARD DECAY]
   
    Soft is safer — it degrades instead of vanishing — but needs a decay
   curve you'd have to pick. [THE THING IS THAT, SOEMTIMES A HARD EXPIRY IS BETTER, SOMETIME A SOFT EXPIRY IS BETTER ? I DONT MIND CHANGING THIS LATER IF REQUIRED, GO WITH HARD DECAY FOR NOW AS IT WILL BE SIMPLER RIGHT, MAKE IT SIMPLE AND THEN WE CAN GO WITH SOFT DECAY LATER RIGHT ?]

2. Who sets it? Only `remember()`'s classifier, or also a heuristic for
   `tool_outcome` (e.g. a weather/price tool's output is volatile by nature of
   the tool)? [THE TOOL OUTCOME IS COOL IDEA, WE SHOUDL PUSRUE IT LATER AND NOT WORRY ABOUT IT FOR NOW]
   > **Resolved:** the proposal is the latter — an optional per-tool default
   > volatility (e.g. a weather/price-lookup tool's outcome defaults to
   > short-lived unless the classifier overrides it), layered *on top of* the
   > per-item LLM judgment, not instead of it. Per Concern 3's warning against
   > building taxonomies speculatively, defer the tool-level layer until the
   > per-item mechanism exists and is in use — start with just the classifier
   > field.

[LET THE LLM DO IT, WHY NOT LEAN ON THE PEOPLE WHO HAVE FIGURED IT OUT, BECAUSE THE TOOL I WILL HAVE TO DEFINE SO I CAN DO IT LATER]

3. Does an expired-but-referenced fact block artifact GC (Concern 4)?
   > **Clarifying note:** `gc_artifacts()` (`memory.py:441-450`) treats any
   > `MemoryItem` with a non-null `artifact_id` as "referenced," full stop —
   > it doesn't check whether that item is itself stale [WHAT DO YOU MEAN ?]. Open question: once
   > an item is past `expires_at`, should it still count toward keeping its
   > artifact alive, or should expired items drop out of the referenced-set
   > so their artifacts become GC-eligible too? [THEY SHOULD DROP OUT RIGHT ?] Leaning toward "still
   > counts" — expiry is about retrieval relevance, not about whether the
   > underlying artifact bytes are worth keeping — but not decided [I MEAN THE ONLY ISSUE IS THAT, IF YOU HAVE DROPPED OUT THE MEMORY, WE HAVENT BUILT A SYSTEM YET, TO BE ABLE TO PULL THINGS FROM THE ARTIFACT IF MEMORY IS EXPIRED AND THE HASH IS NOT THERE, WE WANT TO BUILD IT EVENTUALLY BUT CNAT DO THAT RIGHT NOW].
4. **(new)** Preferences need overwrite-on-contradiction, not just decay —
   e.g. a newly stated preference should *supersede* an old one, not just
   outscore it at read time. Undesigned; flagged for a later pass, not this
   one. [ THE ISSUE IS THAT, PREFERENCES SHOULD BE OVERWRITTEN BUT IT REQUIRES A LOT OF NUANCE AS EVERY HUMAN DEPENDING ON THE SITUATION HAS DIFFERENT WAYS TO DO THINGS ON MOODS, SO TO DO IT BECAUSE WE NEED TO WORRY ABOUT IT, ITS ABOUT THE NEXT PHASE NOT NEEDED FOR FUNCTIONING RIGHT NOW]

---

## Concern 2 — Cross-run context bleed (the self-conditioning loop)

**Your sharpest catch in the deep-dive (§2.1), and confirmed live in code.**

**The problem:** `agent7.py:179` reads memory at the top of every round with no
`kinds=` filter, no recency weighting, and no run-scoping. So a completely
unrelated `tool_outcome` from a previous run can steer the current run, purely
because it's the nearest cosine match in a small store. You compared it to a
Hermes-style self-learning loop — structurally that's exactly what it is, but
**without any of the safeguards** such a loop needs (no recency decay, no
run-boundary awareness, no relevance floor). [JUST STOP THIS THEN, WE DONT NEED TO HAVE THIS, UNTIL WE CAN FIX IT AND ODO IT PROPERLY, MEMORY]

**Why it's a concern, not just Phase 4b:** Phase 4b (pass `kinds=` where the
caller knows the type) is the *cheap slice* — it stops facts and tool_outcomes
from bleeding into each other where the intent is known. But the real question
is philosophical and you raised it yourself: **do you even want past runs to
condition future runs at all?**

[LETS DO THIS LATER, I DONT WNAT TO HAVE TO LOOK AT THIS RIGHT NOW, IF YOU THINK THERE IS REAL VALUE THEN WE CAN LOOK AT LATER DEFINITELY, BUT RIGHT NOW THIS REQUIRES A LOT OF WORK, NO NEED TO PUSH THIS NOW]

- If **yes** (memory should make each run smarter with accumulated context),
  then you need the safeguards: recency weighting, a relevance floor
  (Concern 5 overlaps), and probably volatility (Concern 1).
  > **Resolved — leaning "no":** the value of contextual carryover is real
  > for durable facts/preferences (those should genuinely accumulate across
  > runs) but murky-to-absent for raw tool outcomes. Knowing "tool X took 3
  > minutes last time" doesn't change what the agent should *do* this run
  > unless something is explicitly watching for that pattern (a retry-budget
  > or timeout policy), which this architecture doesn't have [THEN WHAT ARE WE ACTUALLY DOING THIS FOR ?]. Worth a quick
  > look at how other memory-equipped agents draw this line before designing
  > further — but absent that research, the default is: durable
  > facts/preferences carry over, `tool_outcome` does not, by default.
- If **no** (each run should reason fresh, only pulling durable user
  facts/preferences, never prior tool outputs), then the fix is the opposite:
  *exclude* `tool_outcome` from top-of-run retrieval by default, and only pull
  it when a goal explicitly asks.
  > **Resolved:** yes, this is the adopted stance — exclude `tool_outcome`
  > from default top-of-run retrieval; pull it only when a goal explicitly
  > references prior work (ties into Concern 4's reuse mechanism).

**The tension in your own words:** contextualised memory makes *that* run the
best-performing run (max context) — but risks dragging the *next* run in the
previous run's direction. That trade-off is the actual decision. It's not a
bug to fix; it's a stance to take.

**Open sub-questions:**
1. Is prior-run `tool_outcome` an asset or a liability at retrieval time?
   > **Resolved:** take the liability view for now — add to `TODO.md`. The
   > deeper point raised while resolving this is itself a resolution:
   > **without a wrapper/planner layer that reasons across goals (something
   > like control theory), this architecture has no mechanism to reconcile
   > prior-run `tool_outcome` against the current goal anyway.** "Deep work
   > block" one run and "dinner invites" the next aren't in tension *to the
   > agent*, because nothing here plans across runs. That's a separate,
   > larger feature (a scheduling/planning layer), not a Memory retrieval
   > concern. So excluding `tool_outcome` from default retrieval isn't only
   > the safer choice, it's the only choice that matches what the current
   > single-loop architecture can actually act on. Reopen only if/when a
   > cross-run planner is built that's designed to reason across goals.
2. If asset: recency-weight it or floor it — with what curve/threshold?
3. Does run-scoping (only "my run + durable facts") belong here, and does it
   need the loop to pass a run boundary Memory currently doesn't know about?
   > **Resolved:** facts and preferences get free rein (no run-scoping) for
   > now; run-scoping applies only to `tool_outcome`, per the resolution
   > above. The oscillation worry (prefers reading X but not today,
   > mood-dependent) is real and unsolved — but the decision is to *not*
   > build preference-oscillation handling now rather than build it badly.
   > Leave-it-alone-until-forced is the right call here, not a gap to close
   > speculatively.

---

## Concern 3 — The fact / preference / scratchpad taxonomy ("black hole")

**Your words (§3.1): "a good idea, but really a black hole in terms of
implementation, because the surface area is too large for things to break."**

**The problem:** the only place the four kinds get *decided* from ambiguous
input is `remember()`'s single LLM classifier call (`memory.py:329-355`), on
one pass, with no worked fact-vs-preference examples in the prompt. There's no
deterministic rule distinguishing "user reacted this way" (arguably a `fact`
about a past event) from "user prefers to be told things this way" (a
`preference` about future behaviour). It's whatever the classifier decides,
unaudited.

[SO THIS IS CONTEXT, THAT I CAN WORK WITH CLAUDE, AND GET IT DONE.]

This is particularly hard to do well, since good classification requires deep
context about the user that the model doesn't reliably have yet — which is
exactly why this stays a tripwire, not a build. [AND THIS NEEDS TO BE BUILT OVER TIME, BUT WE NEED TO CONTINOUSLY BE BUILDING THIS OVER TIME]

**Why it's specifically dangerous:** the `scratchpad` vs. everything-else call
has an asymmetric failure cost —
- misclassify a durable fact as `scratchpad` → it silently skips embedding
  (`_EMBEDDABLE_KINDS`) and becomes **permanently unsearchable.** The risk is
  bounded, though — this costs one annoyed re-prompt telling the agent to redo
  it, not data loss.
- misclassify transient scratch as `fact` → it feeds straight into Concern 1's
  stale-fact pile. This is the more dangerous direction: a passing dislike
  could get stored as a standing preference, or a one-off "keep it short"
  could get generalized into "always summarize everything," with no audit
  trail to catch or correct it.

  [THE ISSUE IS THAT, WE DONT HAVE AN AUDITING HERE, THAT NEEDS TO BE BUILT, SO I CAN SEE THINGS, BECAUSE IF THIS MISSCLASSIFYINF HAPPENS AS A FACT, FIXING THIS OVER TIME, WILL EB REALLY HAD, AS IT WILL REQUIRE MUTLIPLE CALLS TO FIX THIS, I MEAN DEPENDS ON THE DECISION ABOVE]

**Why it's a concern, not a plan item:** the tempting fix (a richer taxonomy,
more classifier examples, a validation pass) is *exactly* the scope creep you
flagged. Building a "correct" taxonomy speculatively is how the surface area
blows up. Per your own answer to Open Question 2 (keep write-everything, no
ranker), the disciplined move is: **don't formalise this in the abstract.**
Wait for a live trace (Phase 0) to show a *concrete* misclassification that
actually hurt, then fix it with that real example — not a hypothetical
taxonomy.

**So the "concern" is really a tripwire:** flagged, watched, deliberately NOT
built yet. The thing to come back to is: *has a real misclassification bitten
us yet?* If not, leave it alone. [AUDITING SOFTWARE IS NEEDED, IS NEEDED, WE NEED A FRONT END TO AUDIT, TO SEE WHAT MEMEORY HAS WHAT ARTIFACT HAS, THINGS THAT I CAN THEN CHANGE ? I GUESS IDEALLY YOU SHOUDL BE ABLE TO CHANGE, OVER PROMPTS, OVER PROMPTS.]

> **Decided:** do not build this now. Come back only if a live trace shows a
> concrete misclassification that actually caused a problem — occasional
> misclassification is an annoyance, not a blocker, and isn't worth the
> taxonomy work today. [YES PARK THIS TO DO FOR LATER]

---

## Concern 4 — Artifact directory + dedup-by-input (don't redo work)

**Your comment (§1.5): maintain a directory so we can pull information from
different runs instead of re-running it, and so tools know what's already been
done and don't duplicate work.**

[LETS DO THIS LATER, PARK IT IN TO DO, THIS I S ADDING COMPLEXITY FOR NOW REASON]

**The problem:** content-addressing dedups by *output* (same bytes → same
hash → no re-store). But it does **not** dedup by *input* — fetch the same URL
twice and you do the fetch twice (network, latency, cost), and only *after*
fetching do you discover the bytes were identical. There's no "have I already
fetched `https://x.com/y`?" index anywhere. And there's no cross-run
"here's what this agent already knows/did" catalogue for tools to consult
before acting.

> **Resolved:** agreed this is worth having, with one hard constraint on
> *how*: input-dedup must never become a gate that restricts what the agent
> can fetch or ask for. It should only ever *offer* — "here's what was
> already fetched for this input, reuse or refetch?" — as information
> surfaced to the LLM, never a silent substitution or a hard block. Imposing
> allow/deny-lists on tool calls risks degrading agent performance in
> hard-to-predict ways, and that's a worse trade than the wasted duplicate
> fetch this concern is trying to avoid. The "how exactly" (a normalized-URL
> or tool+args hash index, separate from the content hash) is still
> undesigned — tracked as a TODO, not scheduled.

**Why it's genuinely hard (your own note: "hard to build correctly"):**
- Input-dedup needs a *second* key (hash of the input/URL/args), separate from
  the content hash the store uses today. That's a new index with its own
  staleness question (a URL's content changes over time — when is a cached
  fetch too old to reuse? → overlaps Concern 1). 
- A cross-run "what do we already know" directory is basically a second
  retrieval system layered on Memory, and risks re-introducing exactly the
  bleed problem of Concern 2 (pulling stale prior-run work as if current).
  > **Resolved:** this is a fair distinction, not a rename of Concern 2.
  > Artifact reuse doesn't infer relevance or rerank anything — it just
  > serves back content the agent explicitly searched for and would have
  > fetched anyway; the LLM still does all synthesis and relevance judgment
  > on the same footing as a fresh fetch. That's structurally different from
  > Concern 2's problem, where an *unrelated* prior tool_outcome gets pulled
  > in as if it were relevant to the current query. There's a milder version
  > of bleed possible here too (see sub-question 2 below), but it's a
  > prompt-design problem, not an architectural one.

**Why it's a concern, not a plan item:** the *mechanism* pieces (`list()`,
metadata) are in the implementation plan (Phase 5a) and TODO §8 — but the
*policy* ("when is a cached result fresh enough to reuse instead of redoing
the work?") is an unsolved design question that touches freshness, trust, and
cost all at once. Build the `list()`/metadata primitives first; decide the
reuse policy deliberately, later, with those primitives in hand.

> **Decided:** not required for Phase 1. Build `list()`/metadata primitives
> when they're needed for something else; treat the reuse *policy* itself as
> a backlog item, not a near-term commitment — skepticism here is warranted
> since LLM performance should never be traded away for a caching win.

**Open sub-questions:**
1. Dedup-by-input: what's the key (raw URL? normalised URL? tool+args hash?)
   and what's the freshness window?
   > **Resolved:** freshness window = however long artifacts are retained
   > overall (e.g. a month, matching current artifact retention) — the two
   > are the same knob, not two separate ones. Zooming out, this is the same
   > open question the KG and vector-index designs will eventually have to
   > answer too (their "freshness" is implicitly "forever," which isn't true
   > either — the world changes). → tracked as a TODO in each respective
   > database's own folder/notes, not resolved here.
2. Cross-run reuse: is "reuse prior work" the same feature as "cross-run
   memory bleed" (Concern 2) wearing a friendlier name? Where's the line
   between helpful reuse and stale contamination?
   > **Resolved:** no — see the Concern-4-vs-Concern-2 distinction above.
   > There is a milder bleed risk worth naming: searching "biology mechanics"
   > and later "robot mechanics inspired by biology" might surface the first
   > search's articles as if automatically relevant to the second, when they
   > may not be. Not judged a major issue; addressable through prompt design
   > (present them as candidates to evaluate, not answers) rather than an
   > architecture change.

---

## Concern 5 — Hybrid / RRF retrieval (vector + keyword together)

[PARK THIS FOR NOW, ADD TO DO]

**The problem:** today retrieval is strictly sequential — vector first, and
keyword *only if vector returned literally nothing* (`memory.py:210-219`).
(No, keyword search does not run on FAISS — it's the separate Session-6
lexical/token-overlap path, `_keyword_search` in `memory.py:145-166`; it
scores on token-set overlap between the query and each item's
`keywords`/`descriptor`. FAISS is the vector-only path, `_vector_search`,
`memory.py:171-200`.) A weak-but-nonzero vector hit currently *blocks* the
keyword fallback from ever running, even when keyword would've done better
(this interacts with Concern 5's cousin, the missing similarity floor —
Phase 4a). The module's own docstring already names the intended future:
*"Vector retrieval only. Hybrid retrieval with RRF arrives in a future
session."*

**Why it's a concern, not a plan item:** true hybrid retrieval (run both,
merge/re-rank with something like Reciprocal Rank Fusion) is a real chunk of
design — merge strategy, weighting, dedup across the two result sets. **But**
my honest read (from the deep-dive) is that you might get *most* of the benefit
far more cheaply by doing two smaller things first: (a) the similarity floor
(Phase 4a) so a bad vector hit stops masquerading as success, and (b) letting
keyword run *in addition* when vector confidence is low. Only reach for full
RRF if, after those, retrieval quality is still the bottleneck.

> **Resolved:** agreed this can meaningfully hurt retrieval quality and
> shouldn't be put off indefinitely, but it's not blocking anything today.
> Added to `TODO.md`.

**So the thing to come back to is a decision:** cheap-guards-first (Phase 4a +
"run keyword when vector is weak"), then *measure*, then decide whether full
hybrid/RRF is still worth its complexity. Don't build RRF speculatively.

**Open sub-questions:**
1. After the Phase 4a floor lands, is retrieval quality actually still a
   problem? (Can't answer without Phase 0 + real queries.)
   > **Resolved:** assume yes — retrieval quality will keep mattering more as
   > stored volume grows. This is a weak way to answer the question
   > (assumption, not measurement) but good enough to justify keeping it on
   > the backlog rather than dropping it.
2. If yes: merge strategy — RRF, or simpler score-normalisation-and-combine?
   > **Decided:** keep the current sequential vector-then-keyword-fallback
   > approach for now; don't build RRF or score-normalisation-and-combine
   > speculatively. Added to `TODO.md` for later evaluation once Phase 4a
   > (similarity floor) has landed and been measured.

---

## Concern 6 — The "write everything, filter on read" bet

**Status: you already answered — confirmed KEEP for now (§3.6). This is here
only to record the trigger for revisiting, so it's a conscious bet, not a
default that drifted in.**

**The bet:** every user query, every tool outcome, every document chunk is
written unconditionally and kept forever; there's no "is this worth
remembering" gate anywhere. The trade is: unbounded storage growth in exchange
for never having to build (and never being wrong with) a write-time relevance
classifier. [YES NO THIS NEEDS TO CHANGE, WE NEED TO WORK ON THIS MORE, SO WE CAN DECIDE THIS IDEALLY AGAIN AND DO MORE OF THIS, BECAUSE YES FOR NOW KEEP IT BUT PARK IT IN TO DO WILL NEED OTO BE LOOKED AT]

> **Deferred, per standing decision:** the hard part is exactly "what counts
> as worth remembering," which is the same taxonomy problem as Concern 3 —
> don't design it in the abstract; revisit only when a live trace shows a
> real cost.

**Why keeping it is right, right now:** a bad filter silently drops something
that mattered (unrecoverable); over-storing just adds retrieval noise
(recoverable by better ranking). At current scale (hundreds of items) noise is
cheap. And a write-time "should I remember this" classifier is precisely the
large-surface-area machinery you (rightly) don't want to build speculatively.

> **Supporting note:** this is a personal, single-user system — the
> realistic write volume (hundreds to low thousands of items) makes the
> "unbounded storage growth" cost close to theoretical. This makes KEEP an
> even easier call than the general case; noise from over-storing is unlikely
> to become annoying at this scale before something else (Concern 1 or 2)
> does.

**The trigger to revisit (write it down so it's not vibes):** revisit *only*
when a live trace shows the store genuinely degrading answer quality — i.e.
relevant hits getting crowded out by irrelevant ones that ranking can't fix.
Until that's observed, do nothing. Note that Concern 1 (volatility) and
Concern 2 (bleed) will likely bite *before* raw volume does — so if answer
quality drops, suspect *those* first, not the absence of a write filter.

> **This is the meta-takeaway from the whole document, promoted to its own
> item:** auditability is genuinely important and nothing built so far has a
> feature for it. See **Concern 8** below.

---

## Concern 7 — `_index()` reload on every read (parked-tier efficiency)

[THIS IS ACTUALLY SOMETHING YOU CAN DO EASILY AS THATS NOT SOEMTHING I NEED TO LOOK AT, CLAUDE CODE OR CODEX CAN DO IT VERY WELL I GUESS AND PRETTY EASILY, WHAT AM I GOING TO ADD TO SOMETHING HERE ESPECIALLY SINCE THIS IS PRETTY SIMPLE]

**Status: lowest priority, explicitly parked. Here for completeness.**

**The problem:** `_index()` does a full FAISS-file reload + full id-list
drift-check on *every single* `memory.read()`, even twice in a row in the same
process with nothing changed (`memory.py:86-108`, `DEEPDIVE.md` §2.5).

**Why it's parked, not planned:** the obvious fix (cache the loaded index
in-process, invalidate on write) reintroduces cross-process cache-coherency
complexity — the mcp_server subprocess writes to the same files independently,
so an in-process cache in the main process can go stale silently. At current
scale the reload is genuinely cheap (small JSON + small FAISS index = low
milliseconds), so the correctness risk of a stale cache is a *worse* trade than
the CPU cost of reloading.

**Come back only if:** live profiling (which needs Phase 0) shows `_index()`
actually costing meaningful time. Until measured, leave it. This aligns with
the standing "correctness first, no efficiency work until the loop is correct"
rule. [YEAH I GUESS AS WELL, IF ITS SIMPLE, THE ISSUE IS THAT MAYBE THIS CACHE IS DIFFICULT FOR ME TO UNDERSTAND AND CONTRIBUTE HERE I GUESS]

> **Decided:** stay parked. Nothing in this review pass surfaced new
> information that changes the tradeoff — the correctness risk of an
> in-process cache going stale against the MCP subprocess's writes is still
> worse than the cost of the reload at current scale. Revisit only when
> Phase 0 profiling exists.

---

## Concern 8 — Auditability (cross-cutting, meta)

**Status:** newly surfaced 2026-07-08 while resolving comments on Concerns
1–7. Not analyzed in the deep-dive; flagged here so it isn't lost.

**The observation:** every concern above — volatility (1), cross-run bleed
(2), taxonomy misclassification (3), artifact reuse (4), retrieval quality
(5), write-everything (6) — shares a missing piece: **there's no way to see,
after the fact, why the system did what it did.** Which classifier call
decided this was a `fact` and not a `scratchpad`? Why did this item's
`expires_at` end up set to that date? Why did this artifact get GC'd? None of
that is captured anywhere today.

**Why it's cross-cutting rather than its own build:** every mechanism
proposed above (per-item volatility, run-scoping, classifier decisions)
becomes easier to trust and easier to debug if its reasoning is logged, even
minimally — e.g. store the classifier's raw output alongside the final
`MemoryItem`, not just the parsed fields. This doesn't need a new subsystem;
closer to "log what `remember()`/`gc_artifacts()` already compute, and don't
throw it away."

**Why it's not a plan item yet:** it doesn't block anything currently
working, and building it before there's a real audit need (a wrong
classification, an unexpected GC) risks the same speculative-machinery trap
as Concern 3.

**Come back to this:** whenever any of Concerns 1–5 actually get built — bake
minimal audit logging into each one at build time, rather than retrofitting
it later.

[YEAH AUDITABILITY, IS REALLY REALLY IMPORTANT, SOMETHIGN WE SHOUDL DO, JUST NOT RIGHT NOW]

---

## How these relate (one map)

```
Concern 1 (volatility) ──┬── feeds ──> Concern 2 (cross-run bleed)
                         │              (stale fact = worst bleed case)
                         └── overlaps ─> Concern 4 (cached-fetch freshness)

Concern 2 (bleed) ─── cheap slice is Phase 4b (kinds= filter)
                  └── real fix is a STANCE, not code — decided: exclude
                      tool_outcome from default retrieval

Concern 5 (hybrid) ─── cheap guards first (Phase 4a) ── then measure ── then decide

Concern 3 (taxonomy) ─── a tripwire: watch, don't build
Concern 6 (write-all) ─── decided KEEP; trigger recorded
Concern 7 (reload)   ─── parked; unpark only on measured slowness
Concern 8 (auditability) ─── cross-cutting; bake in when 1-5 get built, not before
```

**If you only reopen one:** Concern 1 (volatility), because it's the root cause
feeding 2 and 4, it's the one that produces *wrong answers* rather than just
noise, and it's the one that most needs a deliberate design pass rather than a
patch. If you want the single meta-lesson from this whole review pass, it's
Concern 8: whatever gets built first should log its own reasoning from day
one.
