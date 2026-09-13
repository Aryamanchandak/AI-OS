# System Architecture — Working Doc

Purpose: track the layout/connection decisions for unifying the UI and backend, one at a time. This is a decision log, not the product plan — see `PROJECT_PLAN_CONSOLIDATED.MD` for the product thesis and scope.

Status key: 🟡 open (needs your call) · ✅ decided · 🔲 not started

---

## The model, precisely (revised after Q2/Q6c)

- **Dining room =** `shell`**.** The one human-facing surface. Its own independent app — decided in Q1, calls `gateway` over HTTP.
- **Waiter =** `gateway`**.** Front door only. Auth, request in, hand-off, response out. Owns the one public address. **Not** the intelligence — just the doorman.
- **Main Loop / Planner = the promoted** `AI Agent` **loop.** The actual brain, living behind `gateway` (same process/deployment boundary — no new service to stand up). Decides which chef(s) to call, in what order, whether to loop again. Chefs report to the Main Loop, never to `gateway` directly (Q2).
- **Judge/Critic agent.** A separate ReAct-based agent advising the Main Loop on when to stop. Possibly related to `Assignment 8`'s Planner/Executor/Critic DAG Agent — worth checking before building fresh.
- **The chefs — your specialists** (Veritas, Steelman Generator, Decision Tracker, Mirfish/Mental Models, PraxisEngine), each with its own internal loop (leaning ReAct). They live alongside/under the Main Loop's codebase (Q5), not scattered, not under `gateway` directly.
- **Fridge/pantry =** `Database/` **+** `ingestion-pipeline`**.** Reachable only through a query function (`ask_my_data`), called by the Main Loop or a chef that needs it (e.g. Veritas) — never browsed directly by `shell` or `gateway`.

Revised shape:

```
shell  →  gateway (doorman only)  →  Main Loop (planner, = AI Agent)  →  chefs (own loops)
                                            ↕
                                    Judge/Critic agent (stop/continue)
```

Everything still sits "under gateway" in the outer sense (Q7) — `gateway` is the outermost boundary of the backend, one process/deployment — it's just not the thing making decisions inside that boundary.

---



## Core rule (decided, not up for relitigating)

✅ **No peer-to-peer calls between chefs, and no chef calls back into the gateway on its own.** A specialist's internal loop (Veritas going back for more evidence, Steelman iterating, etc.) is a private implementation detail — from outside, a specialist is one request in, one response out, however much looping happens inside. Only `gateway` is allowed to call more than one specialist for a given request. This keeps the shape a strict two-level hierarchy (`shell → gateway → specialists`) instead of a mesh where anything can call anything. This rule is enforced by *not writing* certain code paths (never give a specialist another specialist's address), not by new infrastructure.

---



## Open questions — work through in order



### Q1. ✅ DECIDED — `shell` is independent from `gateway`

Your call, overriding my earlier lean toward folding them together: `shell` stays its own app, calls `gateway` over HTTP. Implication to carry forward: because they're two separate deployables, you still need *some* contract-sync mechanism between them (even same-language, drift is possible) — likely a lighter version of what already exists between the current React `shell` and `gateway` today. Not a blocker, just don't drop it when the rewrite happens.

### Q2. ✅ DECIDED (revised) — Chefs connect to the Main Loop, not to `gateway`

Correct catch — `gateway` was doing two jobs in my draft (doorman + brain). Split: `gateway` only relays; the **Main Loop** (promoted `AI Agent`, see Q6c) is what actually calls each chef, when needed. The two implementation options from the original draft (thin HTTP wrapper per chef vs. calling existing MCP servers directly) still apply — just re-target them: it's the **Main Loop** that holds the registry and makes the call, not `gateway`. Revisit which option (new wrapper vs. reuse existing MCP servers) once Q3 gets its real session.

### Q3. 🟡 OPEN — deliberately not decided here; needs its own dedicated pass

Agreed, this isn't a glance-over. This is the actual communication contract between the Main Loop and every chef, and its shape depends on decisions not yet made: does a chef's ReAct loop need to report intermediate steps to the Main Loop/Judge (streaming), or only a final answer (simple request/response)? Does the Judge agent see raw chef output or a summarized version? Parking this as its own session, after Q6c's Main Loop shape is confirmed — the loop design has to exist before its interface can be designed properly.

**Reference material for that session — findings from reading** `Assignment 8 existing/` **(2026-09-13):**

- It's a Planner/Executor/Critic system for stock comparisons. Planner emits a whole task graph up front; Executor runs it layer-by-layer with real concurrency; Critic sits between one flagged step and its successors. [WHAT I THINK WE SHOUDL DO IS USE PDMA SPECIALLY MADE TO MAKE THE BEST POSSIBLE GRAPH OR SOMETHING, WE THEN USE REACT FOR MOST SUB AGENT LOOPS, ESSENTIALLY MAKE USE OF THE ALREADY MADE LOOP TO EMIT A GRAPH AND THEN TRAVERSE IT, WHERE A NODE CAN BE SOMETHING AS SIMPLE AS A FUNCTION CALL IN WHICH CASE WE CAN USE FUNCTION GEMMA, AND A FULL SUB AGENT REACT LOOP, AS AND WHEN REQUIRED] 
- **Portable pattern (not code): the Critic's shape.** One named property, strict JSON `{"verdict": "pass"/"fail", "reason": "..."}`, explicitly "a gate, not a reviewer" — no rewrites, no opinions beyond the one property. Good discipline to copy for the Judge agent's prompt design, so the Judge doesn't turn into a second Main Loop. [HOW WILL YOU MAKE THE CRITIC IS THE BIG QUESTION AND FOR NOW I DONT THINK WE SHOULD MAKE A CRITIC, OR ATELAST WE SHOUDLNT SPEND TOO MUCH TIME ON IT, BECUASE THE CRITIC WILL BE A GOOD ONE BECAUSE I WANT IT TO BE ABEL TO SPIN OFF SUB GRAPHS CONNECTED TO THE MAIN GRAPH.CAN IT BE THE SAME PDMA, JUST WIHT MORE CONSTRAINTS ?]
- **Portable pattern: the recovery classifier** (`agent/recovery.py`). Pure Python, no LLM call — pattern-matches the Critic's failure-reason text into one of 5 fixed strategies (retry / refetch upstream / recompute / reground / escalate), each with a canned follow-up instruction. Cheap way to decide "what do we auto-retry" without burning an LLM call on the decision itself. Worth reusing this idea directly for the Judge → Main Loop handoff.
- **Not portable: the graph/Planner machinery itself.** It plans the whole DAG upfront and only patches it reactively — a different shape from the step-by-step ReAct loop already chosen for the Main Loop. Don't import this part.
- **Not portable as-is: what the Critic actually checks.** Assignment 8's Critic verifies closed, mechanical properties on structured data ("≥200 price points"). The Judge's real job — "has this decision been checked enough, or is there a real gap" — is a fuzzier judgment call and needs its own prompt written from scratch, even while following the same gate-not-reviewer shape.



### Q4. ✅ Does `glc_v5` sit under `gateway`?

Yes. `gateway` owns the one public port; `glc_v5` becomes internal-only, reachable only from `gateway`. Today `glc_v5` listens on its own port (8111) and a separate piece (S16) on 8113 — for a unified backend, `gateway` should own the single external address, with `glc_v5` and everything else behind it.

### Q5. ✅ DECIDED (revised) — Chefs live under the Main Loop

Your call: chefs live under/alongside the Main Loop's codebase, not under `gateway`. Concretely, once the Main Loop's own home is created (see Q6c), each chef becomes a subpackage or sibling package it imports/calls into — still needs its own thin wrapper (Q2/Q3) so the Main Loop calls a consistent shape rather than each chef's bespoke interface. Independent of this: they still need to actually be in git before any of them can run on a real deployment — most currently live under `Original Code/`, which is `.gitignore`d (Missing Pieces #1). That blocker doesn't move regardless of where they end up living. [ I THINK FOR CODE SEGMENTATION ITS BETTER TO SAY THAT, THE MAIN LOOP SITS OUTSIE THE FOLDER WHERE SUB AGENTS ARE , THEY ARE IN THEIR OWN FOLDER UNDER THE GATEWAY BUT RIGHT NOW THE API TO THEM IS ONLY EXPOSED TO THE MAIN LOOP, WE CAN LATER WOKR ON EXPOSING THE API INDIVIDUALLY AS AND WHEN REQUIRED IF A SPECIFIC USE CASE COMES UP] 

### Q6a. ✅ Do specialists ever talk to each other directly (A2A)?

No. When one specialist's output needs to feed another (e.g. Steelman needs Veritas's fact-check first), the **planner sequences it**: call specialist 1, take its output, include it in the input to specialist 2. This is still hub-and-spoke — specialists never know about each other. True A2A (independent agents negotiating without a central planner) is unnecessary here since you own every specialist; not needed now or later for this system.

### Q6b. ✅ DECIDED — deferred, agreed, moving on

No more theorizing on this one. Computer-use agents / event-driven autonomy stay parked exactly as `PROJECT_PLAN_CONSOLIDATED.MD`'s "Next layer" section already had them. Fits the hub-and-spoke shape later without rearchitecting. Not revisited again unless the plan itself changes.

### Q6c. ✅ DECIDED — `AI Agent` is promoted to the Main Loop / Planner

- **Main Loop = the existing** `AI Agent` **loop**, chosen over `React Loop` and over Claude Code + `mcp_server` (the Constitution review's stated default) because it's better-built and better-functioning. **Confirmed 2026-09-12: this is a deliberate override of the Constitution review's default, not drift back to old code.** Settled.
- **Each chef gets its own loop**, leaning ReAct.
- **New component: a Judge/Critic agent** (ReAct-based), separate from the Main Loop, whose job is telling the Main Loop when to stop vs. go again. Check `Assignment 8`'s DAG Agent (Planner/Executor/Critic) before building this fresh — it may already be most of the pattern.
- Naming (Main Loop's persona — "Chief of Staff," "Business Analyst," etc.) is explicitly parked, not blocking anything.
- Still open, low-stakes: do `React Loop` or the non-promoted parts of `AI Agent` become a chef themselves later (e.g. computer-use), or stay legacy? No rush on this one.



### Q7. ✅ DECIDED — pantry sits behind the Main Loop, inside `gateway`'s outer boundary

Reconciled with Q2/Q6c: `gateway` remains the single outer boundary/process (satisfies "everything sits under gateway"), but the pantry is reached by the Main Loop or a chef that needs it (e.g. Veritas calling `ask_my_data`), not by `gateway` itself, which stays a doorman. `Database/` and `ingestion-pipeline` stay exactly where they are on disk — a data root referenced by config path, never moved inside a code package.

---



## Missing pieces (punch list)

1. 🔲 `**Original Code/` and `Persistent Memory Chats Storage/` are `.gitignore`d.** Every specialist lives inside `Original Code/`. Nothing in there can be deployed to a live URL until it's actually tracked. Blocks deployment and blocks Q5. Needs a deliberate decision on what gets brought into the tracked project.
2. 🔲 `ask_my_data(query)` **doesn't exist.** Veritas can currently only check claims against the open web, not your own stored corpus. This is the composition function over `ingestion-pipeline`'s low-level primitives (`vector_db_search`, `kg_neighbors`). Noted, not a current concern — you'll build it, no further discussion needed here.
3. 🔲 **Specialist adapter contract has no implementation.** `model_forge/adapters.py` defines the shape; no specialist currently exposes an endpoint matching it (Q2/Q3).
4. 🔲 **No decision/trace screen in** `shell`**.** Every current screen is ingestion-review shaped. Nothing shows claim → evidence → counter-case → confidence → final decision, which is what the product's own success criteria require.
5. 🔲 **Two uncommitted submodules.** `glc_v5` and `ingestion-pipeline` both show modified changes. Commit inside each before any top-level restructuring — `git mv` across a submodule boundary is easy to botch.
6. 🔲 **Two backends in practice.** `glc_v5` (8111) and S16 (8113) both currently answer directly. Needs collapsing behind `gateway`'s single port (Q4).
7. 🔲 **Shell rewrite itself** (Q1) — not started, pending the app-boundary decision.

---



## Suggested working order

1. Decide Q1 (one app vs two) — changes everything downstream.
2. Resolve Missing Pieces #1 (`Original Code/` git visibility) — blocks deployment regardless of what else happens.
3. Build the adapter contract + one specialist wrapper (Q2/Q3), starting with Steelman or Decision Tracker.
4. Build `ask_my_data(query)` (#2).
5. Build the decision/trace screen (#4) in whatever `shell` becomes per Q1.
6. Collapse to one public port (#6, Q4).
7. Get the full path live on a real URL.
8. Only then, revisit folder layout with real information about what's actually used.

---



## When does planning end and building start? (exit criterion)

Not indefinite. Planning is done, and the next action must be code, once these are all true:

1. Every Q above has a one-sentence answer (Q3 is the only one intentionally still open, and it gets resolved in its own dedicated pass, not by more general discussion).
2. You can draw the full request path — `shell → gateway → Main Loop → chef → back` — as one line with no "TBD" in it.
3. Q6c's override is confirmed as deliberate.

Once those three are true, the next message in this doc should be a commit, not another question. If a new architectural question shows up *after* that point, it goes in a new dated note at the bottom, not a new pass over the whole doc.

*(Scratchpad — add notes here as decisions get made.)*