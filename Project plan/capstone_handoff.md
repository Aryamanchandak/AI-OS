# Capstone + EAG V3 Assignments — Context Handoff for Claude Code

Fresh session, no memory of the conversation that produced this. Treat everything below as the full history — it's the complete picture, not a partial recap.

## Who this is for
Aryaman (AC2) — fixed income strategist at ICICI Prudential AMC, also an AI engineer building a personal "AI OS": ~30 sub-repos, local-first, one FastAPI gateway + one React shell + one shared LLM gateway + one MCP server as the agent/tool boundary + one shared data root (the "Constitution"). Portfolio's own roadmap was already at "prove one vertical slice, then repeat" before any of this started.

## Two tracks, very different urgency
1. **EAG V3 course capstone (Option B)** — solo, 4-week HARD deadline, cannot slip.
2. **13 weekly EAG V3 session assignments** (Sessions 4–10, 13–18) — overdue, but CAN be late. Sessions 1–3, 11, 12 are graded; Session 19 is submitted and awaiting review. Capstone takes strict precedence over these — do not let work on the 13 assignments delay the capstone.

## Capstone: Option B course rules (non-negotiable)
- Solo, bring-your-own-project. No third-party agent orchestration framework (LangChain/CrewAI/etc.) — own loop code is explicitly permitted, and the existing EAG V3 loop is pre-cleared for reuse.
- Must deploy to a real URL, not localhost. ~$2/month hosting, on the user.
- One clear, checkable one-sentence deliverable.
- 5-minute hard-stop pitch at Session 20: one-liner (~20s) → who does this today / cost when it goes wrong (~45s) → five asks (~90s) → the charter (~60s) → how I'll know it works + one hostile input said out loud (~75s) → scope/team/deployment (~30s).
- Instructor is "Rohan" / "The Admin." Option A (not being used) is 27 pre-built agents on a closed internal platform — not directly comparable.

## How Option B is actually evaluated (confirmed against the course transcript, not just the written brief)
- Option A's "10× tests + 100× bugs" scoring formula does **not** apply to Option B.
- Rohan will not review code by default.
- UI/UX is explicitly not evaluated — don't spend build time there.
- The real bar: the deployed app surviving live/adversarial use, plus the live pitch.
- **Open, unconfirmed:** whether there's a separate post-4-week final submission (possibly video), distinct from the Session 20 pitch. Needs asking Rohan directly.
- Guardrail: if Option A's "Claude/Codex-written tests score zero" rule applies in spirit to B, tests submitted for credit should be hand-written by the user — Claude can help design test scenarios/categories, not the test code itself.

## How we got to the current scope — the arc (useful for understanding *why*, not just *what*)
1. **Started narrow.** Three portfolio candidates considered (Research MCP claim-verification, UPI ledger, Steelman Generator), narrowed to a single agent: verify that source material is true, and verify the user actually understood it — one judgment loop applied twice, not two engines stapled together. This followed explicit pushback against wiring multiple portfolio verticals together, named at the time as "the real four-months trap."
2. **Locked v1.** Person = someone onboarding into a new domain at work. Five asks, charter, two hostile inputs (a source embedding self-claimed "already fact-checked" authority; a fluent-but-subtly-wrong user explanation). Build plan: reuse Research MCP's citation-gate infra + the EAG V3 loop; the new piece is the misconception/understanding-grading layer. Technical core: atomic-claim schema, embedding-similarity claim alignment (nomic-embed-text), an open-source NLI/entailment model, confidence-gating to the human, verdict logging for calibration. Deployment: local data path + thin instance behind one hardcoded auth token on a cheap VPS.
3. **Rohan's actual pushback** (informal — he's himself described as somewhat conflicted/inconsistent on this): too thin, buildable in a day or two, too many existing open-source projects already cover the same ground.
4. **Pivot v2.** The real differentiator isn't the matching technique (that's commodity) — it's routing against the user's *own* accumulated, verified knowledge base (Research MCP's corpus, etc.) instead of the open web. That's not something a two-day clone can replicate.
5. **Broadened deliberately, twice, against Claude's initial narrower recommendation** — the user explicitly overrode caution both times, choosing to make the capstone deliverable the AI OS's own "CEO-Planner" orchestrator: a router/dispatcher that takes a real request, decides which of the user's own already-built specialist agents can answer it, assembles shared context across them, returns one coherent answer. This is framed as accelerating a "CEO/planner orchestration system with Neo4j plan-graphs, ChromaDB semantic memory, Modal-hosted deployment" already on the AI OS roadmap — not new invented scope.
6. **Deeper philosophical reframe: "cognitive debt."** Premise — AI use, done normally, is a withdrawal against the user's own cognition; offloading judgment feels free but the capability atrophies. The fix is AI whose job is to keep handing judgment back to the human (commit-then-check, force the counter-case, track calibration over time) instead of absorbing it. Explicitly a *personal* tool, shaped around one person's life — not an institutional deployment. This mapped directly onto existing, mostly-shelved AI OS pieces rather than requiring new invention:
   - **PRAXIS** (aka the focus-agent) was already specced as "situation-in, targeted-principle-out, with a closed scoring loop feeding into the decision tracker," with a synthetic-situation practice mode planned as secondary and never built — that shelved mode *is* the mastery-via-repetition engine the user wants.
   - **Model Forge** (mental-model-builder) is centered on causal structures that emit falsifiable predictions — score those via Decision Tracker and mental-model quality becomes a real number over time, not a vibe.
   - **Mirfish**'s causal-DAG scenario engine (built for market knock-on effects) is a working technical template for generating realistic branching scenarios — same pattern, aimed at personal work situations instead of news events.
   - **Decision Tracker**'s Brier scoring, broken out by category, is what would make proactive blind-spot detection possible ("you're systematically overconfident about X"), not just reactive correction.
   - **Learning System**'s FSRS spaced repetition already exists for facts — same forgetting-curve principle should resurface *specific* flagged misconceptions over time, not just fresh material.
   - Known unsolved problem, flagged honestly rather than claimed solved: nothing forces a professional to volunteer for blind-spot-exposing practice the way a coach forces an athlete's reps. The closest lever available is making the calibration score itself visible enough to create its own pull.
7. **Added a life-priority/calendar ask.** The user wants genuinely autonomous, continuous re-prioritization driven by calendar + task backlog + other knowledge stores — explicitly not just reactive. The existing Planner/Reminders agent is macOS/AppleScript-bound and fails the deployment rule as built. Resolved: rebuild calendar integration headless (Google Calendar API / CalDAV). For the 4-week build, ship the **reactive** version only — folded into an upgraded ask #5 (not a 6th ask, since the pitch format requires exactly five) — and simulate "continuous" for the live demo via simple timer-based re-polling of that same reactive check, not true event-driven autonomy. True autonomous re-prioritization is named explicitly as the next layer, not 4-week scope. Rationale: real calendar OAuth integration plus a genuinely autonomous background-triggered system is a different, larger engineering class than "wire into an already-built specialist," and a live autonomous system failing during the pitch is a worse failure mode than a reactive agent giving one wrong answer.

## CURRENT LOCKED STATE

**One-liner:** An orchestrator that takes what I need to figure out and routes it across my own already-built specialist agents — research/verification, understanding-diagnosis, argument stress-testing, calibration, life-priority — through a shared memory layer, not stapled scripts.

**Person:** the user himself, at his actual job — not a hypothetical generic new-hire. Easier to defend live since he can speak from what actually happened.

**Five asks:**
1. Is this claim actually true, and where did I already establish that? → routes to Research MCP / accumulated corpus
2. Did I actually understand what I just read, or just recognize the vocabulary? → understanding-diagnosis specialist (the core genuinely-new build)
3. What's the strongest case against my current view on this? → routes to Steelman Generator
4. What did I predict here before, and was I right? → routes to Decision Tracker
5. Given my calendar and backlog, what should I actually be doing right now, and does it survive everything above? → new life-priority specialist (real calendar integration + backlog store). Ships **reactive** in 4 weeks; "continuous" feel in the demo comes from timer-based re-polling of the same check, not a new autonomous architecture.

**Charter:** owns routing decisions, cross-agent context assembly, and final prioritization against calendar/backlog. Delegates domain judgment to whichever specialist actually owns that ask. Never fabricates an answer when no specialist covers it — surfaces the gap instead of guessing. Always hands the final "act on this or not" call to the human.

**Hostile inputs to demonstrate:**
1. Source material embedding a self-claimed "already fact-checked" authority marker.
2. A fluent-but-subtly-wrong user explanation.
3. A query engineered to make the router misclassify which specialist should handle it, or skip verification entirely (also covers a manipulated "urgent" flag on the calendar/priority ask).

**Deployment:** local data path + thin VPS instance behind one hardcoded auth token (pulling forward a bridge-VPS step already on the broader AI OS roadmap). Calendar OAuth tokens need their own real secure storage on that VPS — separate concern from the hardcoded auth token. UI polish and the Ryzen hosting-hardware decision are explicitly decoupled from the 4-week clock — not graded, no deadline, continue after.

**Next layer — explicitly named in the pitch, NOT built in these 4 weeks** (this is deliberate: naming a coherent bigger vision while shipping a disciplined narrow slice is a stronger pitch than half-building everything):
- PRAXIS's synthetic-situation practice mode (generative scenario practice, not just reactive checks)
- Mirfish-style causal-DAG scenario generation aimed at personal work situations
- Proactive blind-spot pattern detection from Decision Tracker's categorized Brier scores over time
- FSRS-spaced resurfacing of specific flagged misconceptions, not just fresh material
- True event-driven autonomous re-prioritization (system acts/notifies without being asked)
- The "fading scaffold" — system does less as the user's calibration on a given ask type improves; track hit-rate per ask type first, automate the withdrawal once there's enough data to trust it

**Draft week-by-week** (not yet stress-tested against the actual repo — that's a first task for this session):
- Week 0 (now/already happening): informal check-in with Rohan on this reframed pitch before committing further build time
- Week 1: lock the specialists in scope for asks 1–4 (must already work today — see disclosure below); pick and wire the calendar integration for ask 5; finalize five asks/charter; stand up the orchestrator skeleton with typed Pydantic contracts on the existing gateway/MCP boundary; deploy a bare version to the VPS immediately — retire deployment risk in week 1, not week 4
- Week 2: wire the specialists in for real (real MCP calls, real context/entity passing, real calendar reads); build out the claim-verification + understanding-diagnosis judgment core as one specialist
- Week 3: hostile-input hardening across all attack types; confidence-gating; calibration logging via Decision Tracker; timer-based re-check for ask 5's demo; adversarial test pass
- Week 4: deployment hardening (auth, real usage); replay/trace capture for the pitch; repeated 5-minute pitch dry runs; one buffer day

## IMPORTANT, JUST DISCLOSED — changes the picture materially
Code already exists for **most** of the relevant assignments/specialist components — this is not empty scaffolding. Only 1–2 pieces have no code yet. What exists is "completely vibe coded" per the user — functional-ish, needs a few more iterations before it's genuinely a solid foundation to build on. It hasn't been submitted so far specifically because the user wasn't happy with the code's actual impact, and wasn't confident in his own understanding of what it does — not because it doesn't exist. **The orchestrator loop itself is also already built**, with known room for improvement. This likely resolves most of the "which specialists are actually functional today" open item in the affirmative, but that needs verifying against the real code in this session, not assumed from memory. The user is bringing the actual code and his own comments on this plan into this Claude Code session directly, right after this handoff — expect that to be the next input.

## Open items still unresolved
- [ ] Verify against the real code which specialists (Research MCP / Decision Tracker / Steelman Generator / Mental Model Builder / other) are genuinely solid vs. need the "few iterations" mentioned above
- [ ] Calendar integration choice for ask #5 — Google Calendar API vs. CalDAV vs. other; OAuth scope and token storage on the deployed VPS
- [ ] Backlog/task store for ask #5 — reuse an existing store or build new
- [ ] Claim schema design — the atomic-claim decomposition format shared by source material and user explanations
- [ ] NLI/entailment model choice, benchmarked against actual hardware
- [ ] Confirm whether there's a separate post-4-week final submission
- [ ] Session 18 ambiguity: "one fixed agent config run three times" vs. "three different harnesses" — needs direct clarification from Rohan
- [ ] Session 14's three required invariants — not listed in the brief, check lesson materials
- [ ] Session 6 / Session 8 prescribed queries — not reproduced in the brief, check lesson materials

## The 13 overdue weekly assignments — how they map onto this build (they can be late, the capstone can't)
**Near-free — the orchestrator build already covers the rubric:**
- Session 6 (Memory/Perception/Decision/Action, typed contracts, cross-run memory) — document the orchestrator against this
- Session 5 (qualified prompt → multi-step tool) — the understanding-diagnosis specialist, framed this way
- Session 15 (model routing + budget controls) — route Core LLM calls through the existing shared gateway

**Attempt for real, not forced — check fit first:**
- Session 7 (RAG over 50+ items, meaning-based retrieval) — if Research MCP's corpus clears 50 items
- Session 8 (parallel DAG + Critic + replanning) — source-verification and explanation-grading as concurrent branches

**Ship separately, rubric-minimum, no integration attempt:**
- Sessions 4, 9, 10, 13, 14, 16, 17, 18

## Guardrails established across the whole prior conversation — keep enforcing these
- **Deadline priority is absolute:** the capstone cannot be late; the 13 weekly assignments can.
- **Scope discipline:** this project already got redirected once from stitching many portfolio verticals together into one narrow "one agent, one identity" judgment loop. Every broadening since then has been deliberate and bounded (wire into things that already work, or that are already built even if unpolished) — not a return to that original trap. Hold new asks/features to that same bar; if something needs building from scratch and doesn't clearly serve one of the five asks, it belongs in the "next layer" list, not the 4-week build.
- **No third-party agent orchestration framework, ever,** for the capstone.
- **Tests submitted for credit should be hand-written** by the user, not Claude-authored, if the Option-A rule turns out to apply in spirit to Option B.