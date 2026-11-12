# EAG V3 Capstone — Project Plan (Consolidated)

Consolidated from the annotated `PROJECT_PLAN.MD` — same decisions, comments merged into prose, repetition removed. Original left untouched.

## North star: why this exists

AI use, done the normal way, is a withdrawal against your own cognition — you offload judgment, it feels free, but the capability atrophies ("cognitive debt"), and you lose agency along with the skill. The fix isn't less AI, it's AI whose job is to keep handing judgment back to you instead of absorbing it. That's the pitch, viewed from an upside-down lens: most AI products make you dumber by being convenient; this one is designed to make you sharper by being inconvenient in exactly the right way.

This is a personal tool shaped around one actual life (yours), not an institutional deployment. Everything in your life should have AI woven through it if you want to be on top of this technology and get the most out of it. Right now that's bounded to this codebase and cloud models; a local AI box is coming, and the same design should extend to it.

What that means concretely:

- **Commit before you're checked.** Form a judgment first, then get checked against it (asks #1–#2). Beyond checking what you commit to, the system should actively hunt for claims that need more nuance, surface gaps you didn't know you had, and show you where you're missing something — including places where you've read something and want to follow it but structurally can't yet.
- **Force engagement with the counter-case**, not a verdict (ask #3). *Open question — not yet designed:* what "force engagement" actually means mechanically (block progress until a response is given? require a written rebuttal? something else) still needs to be decided.
- **Track calibration as a real number.** Decision Tracker's Brier scoring, broken out by category over time, is the mechanism — it turns "am I getting better" from a vibe into a number that moves, and it's what makes proactive blind-spot detection possible ("you're systematically overconfident about X") instead of only reactive correction.
- **Mastery through repetition.** An athlete gets thousands of fast, unambiguous, low-stakes reps at escalating difficulty; a professional almost never does. The mechanism for converting expensive real-world learning-by-mistake into cheap simulated learning-by-mistake is PRAXIS's shelved synthetic-situation practice mode, generating scenarios via the same causal-DAG pattern Mirfish already uses for market knock-on effects — aimed at personal work situations instead of news events. There's more in Mirfish worth mining here than just this one pattern; not yet scoped.
- **Fading scaffold.** As your calibration on a given judgment type improves, the system does less of that work for you and asks more of you first — it starts as a checker and becomes mostly a check.

Known open problem, not solved: athletes have a coach forcing uncomfortable reps. Nothing forces a professional to volunteer for a tool that exposes their own blind spots. The closest lever available is making the calibration score itself visible enough that improving it creates its own pull. This is genuinely unsolved, not hand-waved.

## Vision surface vs. 4-week build contract

The ambition here is bigger than five routed asks — this is meant to become an actual AI OS / Jarvis: something that makes you smarter over time through deliberate planning and thought, woven into your real life, not a demo router. The right way to hold that ambition alongside a 4-week capstone deadline is not to shrink the vision — it's to pitch big, YC-style, and build the thinnest slice of it well. Better to ask bigger questions and "underdeliver" cleanly against them than to scope down to something small and fully deliver it. The sections below split accordingly: what the system *is becoming* (unbounded), and what ships in 4 weeks (tightly scoped).

### The AI OS pillar (currently underweighted — needs a real place in the pitch, not a mention)

This is not covered by the five reactive asks and shouldn't be squeezed into them. It's the automation/agency layer of the same system:

- **Graph agents** — worth exploring directly as an architecture, not just as Mirfish's scenario-generation pattern reused elsewhere.
- **A coding/computer-use agent** — can operate the computer directly: read/write/pull files, run things, not just answer in text.
- **Event-trigger agents** — the system acts on triggers, not only on request (this is the precursor to the "true event-driven autonomy" named in the next layer below).
- **Automations of things you currently do manually** — the actual "operating system" half of AI OS, distinct from the "advisor" half the five asks cover.
- **Proactive blind-spot prompting** — surfacing nuance gaps and missed considerations before being asked, not only when a claim is submitted for checking.

Assignment 4's ReAct loop with a research-focused MCP already exists (needs improvement, but ahead of the assignment baseline), as does a PDMA implementation more advanced than the one given in the assignment. Both are candidate substrate for the coding-agent and event-trigger pieces above rather than net-new builds.

## Current direction: AI OS Orchestrator ("CEO-Planner") [I DONT LIKE THE TITLE CEO PLANNER ]

[HOW CAN I MAKE THE MOST OF AI]

**Working one-liner (current):** An orchestrator that takes what I need to figure out and routes it across my own already-built specialist agents — research/verification, understanding-diagnosis, argument stress-testing, calibration, life-priority — through a shared memory layer, not stapled scripts.

**Alternative one-liner (outcome-oriented, evaluate alongside the above):**

> Before I act on a work decision, the system checks my claim, understanding, counter-case, prediction history, and current priorities — then shows me where my judgment may be wrong without making the decision for me.

Important framing: this is mostly already-written code getting a macro-level orchestration pass, not a from-scratch build. It ships the CEO/planner orchestration layer already on the AI OS roadmap, pulled forward onto a forced deadline — which is a feature, not a compromise: the deadline forces more real progress than would happen otherwise.

The distinctive contribution is **not** the router itself — "an orchestrator that connects specialist agents" reads as integration plumbing and invites comparison to generic orchestration products. The real proposition is that normal AI use creates cognitive debt, and this system deliberately requires you to form and expose a judgment *before* receiving assistance, then checks the claim, tests understanding, forces engagement with the counter-case, tracks calibration, and returns the final call to you.

**Who the person is:** you, at your actual job — not a hypothetical generic new-hire. Easier to defend live since you can speak from what actually happened.

### Five asks — working draft, not locked

These are the current best formulation, not a final spec. There's real appetite to ask bigger here as the AI OS pillar above gets folded in — treat these as expandable, not as a ceiling.

1. Is this claim actually true, and where did I already establish that? → Research MCP / accumulated corpus.
2. Did I actually understand what I just read, or just recognize the vocabulary? → understanding-diagnosis specialist (the genuinely new build).
3. What's the strongest case against my current view on this? → Steelman Generator.
4. What did I predict here before, and was I right? → Decision Tracker.
5. Given my calendar and backlog, what should I actually be doing right now, and does it survive everything above? → new life-priority specialist (real calendar integration + backlog store); the orchestrator's own gating decision, with the final call handed to the human. Ships **reactive** in 4 weeks — same ask-and-answer pattern as the other four. The "continuous" feel for the pitch comes from re-running the same check on a timer and surfacing what changed, not from a new autonomous architecture.



### Charter

- **Owns:** routing decisions, cross-agent context assembly, final prioritization against calendar/backlog.
- **Delegates:** domain judgment to whichever specialist actually owns that ask.
- **Never:** fabricates an answer when no specialist covers the ask — surfaces the gap instead of guessing.
- **Always:** hands the final "act on this or not" call to the human.



### The demonstration should be one decision, not five prompts

Ask 5 requires the recommendation to "survive everything above," which means the real capstone is a coordinated decision workflow, not five independent routed tools. If the demo is five unrelated prompts, the product looks like scripts behind a router. Instead, walk **one authentic professional decision** through a coherent path:

1. You record your initial judgment or prediction.
2. The system verifies the important underlying claims against your accumulated knowledge.
3. The system checks whether your explanation reflects real understanding.
4. The system surfaces the strongest counter-case.
5. The system retrieves relevant prior predictions and calibration history.
6. The system evaluates the decision against your current calendar and backlog.
7. The system returns evidence, uncertainty, and identified gaps — you decide.

Not every input must invoke every specialist; the orchestrator should make and expose that decision, including why a specialist was or wasn't called.

### Next layer — what this becomes, not what's excluded

These are the real long-term differentiators. Naming them as the deliberate next step, and pitching them as part of the vision, is stronger than half-building them now:

- PRAXIS's synthetic-situation practice mode — generative scenario practice, not just reactive checks.
- Mirfish-style causal-DAG scenario generation aimed at personal work situations (with more of the Mirfish pattern still unmined).
- Proactive blind-spot pattern detection from Decision Tracker's categorized Brier scores over time.
- FSRS-spaced resurfacing of specific flagged misconceptions, not just fresh material.
- True event-driven autonomy — system acts/notifies without being asked, building on the AI OS pillar's event-trigger agents.
- Automated fading-scaffold withdrawal — track hit rate per ask type first; automate once there's enough data to trust it.



### Hostile inputs to demonstrate (doubles as evaluation criteria)

1. Source material embedding a self-claimed "already fact-checked" authority marker — system should resist it without supporting evidence.
2. A fluent-but-subtly-wrong user explanation — system should catch at least one such case.
3. A query engineered to make the router misclassify which specialist should handle it, or skip verification entirely — including a manipulated "urgent" flag on the calendar/priority ask.



## Course constraints (Option B)

- Solo, bring-your-own-project track (vs. Option A's 27 pre-built agents on a closed platform, code not shared).
- No third-party agent orchestration framework (LangChain/CrewAI/etc.) — write your own loop or reuse your own EAG V3 code (explicitly permitted).
- Must deploy to a real URL, not localhost (~$2/month hosting, on you).
- One clear, checkable one-sentence deliverable.
- 5-minute hard-stop pitch at Session 20.

**How it's evaluated:** the Option-A "10× tests + 100× bugs" formula doesn't apply. Rohan won't review code by default. UI/UX isn't graded — but don't ignore it either; if it can be vibe-coded cheaply, do it, just don't spend core capstone time on it. The real bar is the deployed app surviving live/adversarial use, plus the live pitch. If Option A's "Claude/Codex-written tests score zero" applies in spirit here, tests submitted for credit should be hand-written — Claude can help design test scenarios/categories, not the test code.

**Open, unconfirmed:** is there a separate post-4-week final submission (possibly video), distinct from the Session 20 pitch? Confirm with Rohan.

## Why the scope changed

Original plan: one agent doing claim-verification + understanding-diagnosis (embedding alignment + NLI over source material and self-explanation). Rohan's pushback: too thin, buildable in a day or two, too many existing open-source projects cover the same ground.

Resolution: the differentiator isn't the matching technique (commodity) — it's routing against **your own accumulated, verified knowledge base**, built over months across your AI OS, instead of the open web. A two-day GitHub clone can't replicate that.

## Where the project actually is (as of 9 Sept 2026)

Late Week 0 / entrance to Week 1. Product philosophy, intended user, five asks, and charter are a strong draft (not yet locked — see above), but the capstone has not yet been demonstrated as one verified, deployed, end-to-end product.

- **Product definition:** ~80–90% settled.
- **Reusable technical ingredients:** ~60–75% present (qualitative estimate from the code survey below).
- **Capstone integration:** unproven until checked against the real repositories.
- **Deployment and evaluation readiness:** unproven.

These are planning estimates, not measured scores — existing code isn't capstone-ready just because a component exists or rated well qualitatively.

### What the existing-code survey found

- Assignment 5: Veritas — a research/scientific-claim verification pipeline with citations and self-critique.
- Assignment 8: concurrent DAG reasoning, causal scenario generation, evidence-backed consequence analysis.
- Assignment 13: gateway + agent runtime with task graphs, durable semantic memory, document indexing, A2A interoperability.
- Assignment 15: the most mature runtime/gateway generation — constrained planning, durable graph events, human approval, budget enforcement, telemetry, accounting, allowance policy.
- Lecture 7: an earlier complete iterative agent — planning, MCP execution, artifacts, FAISS memory, model routing, failover, embeddings, call history.

Strongest qualities across the survey: typed contracts, gateway/runtime/tool layer separation, meaningful tests, explicit cost tracking, memory, safety boundaries.

**Main technical risk: duplication.** Multiple generations of gateways and agent runtimes coexist. Before building new functionality, identify which runtime, gateway, memory layer, and specialist implementations are canonical — high individual ratings don't prove these components interoperate or work reliably on real stored data. This is the single largest source of integration risk in the whole plan.

## Single sequenced plan (Week 1 gate → Week 4)

Do not add a specialist, calendar integration, or new ask before Week 1's gate (steps 1–7) is complete.

**Week 1 gate:**

1. Inventory actual candidate repos for Research MCP/Veritas, Steelman Generator, Decision Tracker, Mental Model Builder, the orchestrator, the shared gateway, and memory.
2. Pick one canonical runtime, one canonical gateway, one memory boundary, one data root. Record why; mark older copies non-canonical without deleting them.
3. Run every proposed specialist against real stored data — not examples, not mocks.
4. Classify each specialist: **use now** (works reliably enough to integrate) / **repair now** (bounded, days not weeks) / **exclude from capstone** (needs a rewrite, missing data, or an uncertain external dependency).
5. Select the three strongest specialists for the core demonstration. Five asks can stay in the product vocabulary; implementation depth doesn't need to match.
6. Choose one real work decision as the golden-path scenario; define expected evidence and failure modes in advance.
7. Stand up and deploy the thinnest vertical slice immediately: authenticated request → orchestration trace → at least one real specialist → evidence-bearing response. Retire deployment risk in Week 1, not Week 4.

**Week 1 (remaining):** finalize the five asks/charter against the gate's findings; wire the calendar integration for ask #5 (decide provider only after the vertical slice works — if OAuth threatens the critical path, ship ask 5 with a bounded/manual backlog input first and move full calendar integration behind the deployment milestone); typed Pydantic contracts on the existing gateway/MCP boundary.

**Week 2:** wire the three chosen specialists in for real (real MCP calls, real context/entity passing, real calendar reads); build the claim-verification + understanding-diagnosis judgment core as one specialist.

**Week 3:** hostile-input hardening across all three attack types (converted into explicit human-authored evaluation cases with recorded pass/fail — AI-generated tests don't substitute for credit-bearing tests); confidence-gating; calibration logging via Decision Tracker; timer-based re-check for ask #5's "continuous" demo feel; adversarial test pass.

**Week 4:** deployment hardening (auth, real usage); replay/trace capture for the pitch; repeated 5-minute pitch dry runs; one buffer day.

**Ask Rohan, in one consolidated message:** the separate post-4-week final submission question; Session 18's "one fixed agent config run three times" vs. "three different harnesses" ambiguity; Session 14's three required invariants (not in the brief — check lesson materials); Session 6/8's prescribed queries (not reproduced in the brief — check lesson materials).

## Minimum measurable success criteria

Not "ready" just because all five routes return text. Minimum credible definition of done:

- The deployed URL completes one authentic end-to-end professional decision workflow.
- The router selects the correct specialist(s) for a defined evaluation set and records its routing rationale.
- Outputs distinguish retrieved evidence, model inference, uncertainty, and unsupported gaps.
- The orchestrator abstains rather than inventing an answer when no specialist/evidence source can answer safely.
- All three hostile-input classes above are handled (self-certified source, fluent-wrong explanation, misrouting/urgency manipulation).
- The user's initial judgment is captured before the system reveals its assessment (commit-then-check preserved).
- A prediction/confidence value can be logged and later connected to an outcome/calibration record.
- At least one complete replayable trace is available for the pitch: specialist calls, evidence, confidence, abstentions, final human decision point.
- Calendar credentials are stored separately and securely from the app's simple access token, if calendar integration ships.

Exact numerical thresholds (routing accuracy, latency, cost, hostile-input pass rate) get set after the canonical components have been run and a realistic baseline exists.

## Deployment plan

- Local data path + thin instance behind one hardcoded auth token on a cheap VPS (pulling forward the bridge-VPS step already on the broader AI OS roadmap).
- Calendar OAuth tokens need real, separate secure storage on that VPS — don't conflate with the hardcoded app auth token.
- UI polish and the Ryzen hosting-hardware decision are decoupled from the 4-week clock — not graded, no deadline, continue after.



## Overlap with the 13 overdue weekly assignments (they can be late; the capstone can't)

**Near-free — the orchestrator build already covers the rubric:**

- Session 6 (Memory/Perception/Decision/Action, typed contracts, cross-run memory) — document the orchestrator against this.
- Session 5 (qualified prompt → multi-step tool) — the understanding-diagnosis specialist, framed this way.
- Session 15 (model routing + budget controls) — route Core LLM calls through the existing shared gateway.

**Attempt for real, not forced — check fit first:**

- Session 7 (RAG over 50+ items, meaning-based retrieval) — if Research MCP's corpus clears 50 items.
- Session 8 (parallel DAG + Critic + replanning) — source-verification and explanation-grading as concurrent branches.

**Ship separately, rubric-minimum, no integration attempt:**

- Sessions 4, 9, 10, 13, 14, 16, 17, 18. (Session 4's ReAct/research-MCP baseline and its PDMA are already ahead of the assignment spec — see the AI OS pillar above. A coding agent for computer-use/file operations, and the event-trigger agents, are likely useful substrate across several of these; not yet mapped one-to-one.)



## Recommended scope rule

Prioritize **one compelling coordinated decision flow supported by three genuinely working specialists** over five shallow integrations. A fourth or fifth specialist enters the live capstone only after the deployed golden path works reliably and produces a replayable trace.

## Status, one sentence

> The project has a strong thesis, a mostly settled product definition, and promising reusable components, but it has not yet crossed from a well-designed plan into a verified integrated product.



## Notes / scratchpad

*(add anything here as you go)*