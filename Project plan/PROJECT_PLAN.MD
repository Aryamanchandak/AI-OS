# EAG V3 Capstone — Project Plan

## North star: why this exists

Premise: AI use, done the normal way, is a withdrawal against your own cognition — you offload judgment, it feels free, but the capability atrophies ("cognitive debt") [you start relying on it more and more, while good it makes you loose some intagnible skills and infoprmation which is pretty well researched on, I feel sometimes the human also looses agency]. The fix isn't less AI, it's AI whose actual job is to keep handing judgment back to the human instead of absorbing it [ITS VIEWING AI FROM AN UPSIDE DOWN LENS, AND THIS IS MY PITCH AND UNIQUE PROPOSITION]. This has to be a personal tool shaped around one person's actual life, not an institutional deployment. [EVERYTHING IN YOUR LIFE SHOUDL AI IN IT IS MY POINT OF VIEW IF YOU WANT OT BE ON TOP OF THIS TECHNOLOGY IF YOU WANT TO MAKE THE MOST OF IT, RIGHT NOW MY PERSONAL LIFE IS CLOSED TO THIS CODE AND TO CLOUD MODELS BUT I WILL SOON HAVE A LOCAL AI BOX WHICH WILL GET EXPOSED TO THAT AS WELL]

What that means concretely:

- Ask for a check on a claim, not the claim answered — commit to a judgment first, then get checked (applies to asks #1 and #2 below) [WHAT IT SHOULLD ALSO DO IS ACTIVELY LOOK FOR CLIAMS WHICH REQUIRE MORE NUANCE, WHERE THERE ARE GAPS AND PROMPT THE USER TO FILL THEM AND SHOW BLLIND SPOTS, SHOW THE USER AREAS WHERE THE HUMAN MISSES SOMETHING, WHICH CAN BE PERCEIVED IN A NEW WAY, THINGS THAT RUN AGAINST THE HUMAN THINGS THAT HUMAN HAS READ AND WANTS TO FOLLOW BUT CANT ]
- Force engagement with the counter-case, not a verdict (ask #3) [OK AND WHAT DOES THAT MEAN IF YOU DONT MIND ME ASKING ?]
- Track calibration over time so "getting better" is a real, visible number, not a vibe (ask #4) [YES AND HOW WILL WE DO THIS ?]
- Mastery through repetition: an athlete gets thousands of reps with fast, unambiguous feedback at escalating difficulty and no real cost when they fail; a professional almost never does. The system's job is converting expensive real-world learning-by-mistake into cheap simulated learning-by-mistake. [YES AND THIS IS IMPORTANT NOT SOMETHING TO BE SCOFFED AT, BUT HOW WILL WE DO THIS ?]
- As the human's calibration on a given judgment type improves, the system does less of that work for them and asks more of them first — it starts as a checker and becomes mostly a check (the "fading scaffold") [YES]

[WHAT IS MISSING HERE IS THE AI OS PART, WHERE WE INTEGRATE A FEW THINGS THAT THE HUMAN CAN AUTOMATE, I FEEL LIKE WE ARE GIVING UP ON A PRIME OPPORTUNITY HERE ]



[I ALSO LIKE THE IDEA OF GRAPH AGENTS AND THAT IS SOMETHING I WANT TO EXPLORE WITHOTU A DOUBT] 

This connects directly to existing AI OS pieces, not new invention:

- **PRAXIS** (focus-agent) was already specced as "situation-in, targeted-principle-out, with a closed scoring loop feeding back into the decision tracker," with a synthetic-situation practice mode planned as secondary and never built — that shelved mode *is* the mastery-via-repetition engine [YES AND THATS WHAT MAKES IT USEFUL, HERE WE CAN VIBE CODE, IT DOESNT MATTER SO WE WILL BE DEALING WITH ALMOST ONLY ENGLISH AND A LOT OF TALKING LOL] 
- **Model Forge** (mental-model-builder) is centered on causal structures that emit falsifiable predictions — feed those predictions into Decision Tracker's scoring and mental-model quality becomes a number that moves, not a framework [YES THE QUESTION IS AGAIN HOW IT WORKS AND HOW WE WILL INTEGRATE ]
- **Mirfish**'s causal-DAG scenario engine (built for market knock-on effects) is a working technical template for generating realistic branching scenarios — the same pattern aimed at personal work situations instead of news events [THERE IS MORE WHERE THIS COMES FROM ALSO THAT WE ARENT CONSIDERING YET]
- **Decision Tracker**'s Brier scoring, broken out by category over time, is what makes proactive blind-spot detection possible ("you're systematically overconfident about X") rather than only reactive correction
- **Learning System**'s FSRS spaced repetition already exists for facts — the same forgetting-curve principle should resurface *specific* flagged misconceptions over time, not just fresh material

Known open problem, not solved: athletes have a coach forcing uncomfortable reps. Nothing forces a professional to volunteer for a tool that exposes their own blind spots. The closest lever available is making the calibration score itself visible enough that improving it creates its own pull. Flagging this honestly rather than claiming it's solved. [AGAIN SOMETHING THAT IS LACKING THE AI OS FEATURES THE HUMAN PERSONAL ASSITANT ASPECT] 

Scope discipline: mastery claims should stay scoped to one specific recurring judgment type (the way the five asks already are), not a vague "business mastery" claim that falls apart under questioning — a tennis serve doesn't transfer to golf.

## Course constraints (Option B)

- Solo, bring-your-own-project track (vs. Option A: pick from 27 pre-built agents on a closed internal platform, code not shared)
- No third-party agent orchestration framework (LangChain/CrewAI/etc.) — write your own loop, or reuse your own EAG V3 code (explicitly permitted)
- Must deploy to a real URL, not localhost (~$2/month hosting, on you)
- One clear, checkable one-sentence deliverable
- 5-minute hard-stop pitch at Session 20



## How Option B is actually evaluated

- The Option-A "10× tests + 100× bugs" scoring formula does **not** apply to B
- Rohan will not review code by default
- UI/UX is explicitly not evaluated — don't spend capstone time there [YES BUT DONT IGNORE IT EITHER, IF WE CAN VIBE CODE THIS THEN LETS]
- Real bar: the deployed app surviving live/adversarial use, plus the live pitch [YES ]
- **Open, unconfirmed:** is there a separate post-4-week final submission (possibly video), distinct from the Session 20 pitch? Confirm with Rohan.
- Guardrail: if Option A's "Claude/Codex-written tests score zero" applies in spirit to B, tests submitted for credit should be hand-written — Claude can help design test scenarios/categories, not the test code



## Why the scope changed

Original plan: one agent doing claim-verification + understanding-diagnosis (embedding alignment + NLI over source material and self-explanation). Rohan's actual pushback: too thin, buildable in a day or two, too many existing open-source projects cover the same ground.

Resolution: the differentiator isn't the matching technique (that part is commodity) — it's routing against **your own accumulated, verified knowledge base**, built over months across your AI OS, instead of the open web. That's not something a two-day GitHub clone can replicate.

## Current direction: AI OS Orchestrator ("CEO-Planner")

**One-liner:** An orchestrator that takes what I need to figure out and routes it across my own already-built specialist agents — research/verification, understanding-diagnosis, argument stress-testing, calibration, life-priority — through a shared memory layer, not stapled scripts. [AGAIN AND MORE THAT WE HAVE NOT TALKED ABOUT, YOU NEED TO UNDERSTAND THIS CODE IS MOSTLY ALREADY WRITTEN, WE ARE DOING MACRO VIEW WITH A LOT OF AI INPUT WHERE REQUIRED AND POSSIBLE]

Not new scope invented for class — this ships the CEO/planner orchestration layer already on the AI OS roadmap, on a forced deadline. [YES FORCES YOU TO GET MORE DONE, AND GET AS MUCH DONE AS POSSIBLE]

**Who the person is:** you, at your actual job — not a hypothetical generic new-hire. Easier to defend live since you can speak from what actually happened.

### Five asks

1. Is this claim actually true, and where did I already establish that? → routes to Research MCP / accumulated corpus 
2. Did I actually understand what I just read, or just recognize the vocabulary? → understanding-diagnosis specialist (the genuinely new build)
3. What's the strongest case against my current view on this? → routes to Steelman Generator
4. What did I predict here before, and was I right? → routes to Decision Tracker
5. Given my calendar and backlog, what should I actually be doing right now, and does it survive everything above? → routes to a new life-priority specialist (real calendar integration + backlog store); orchestrator's own gating decision, hands the final call to the human. Ships **reactive** in 4 weeks (ask-and-answer, same pattern as the other four); "continuous" feel for the pitch comes from re-running the same check on a timer and surfacing what changed — not a new autonomous architecture. True event-driven autonomy (system interrupts you unasked) is explicitly next, not in this build — see Next Layer below.

[ I AM NOT HAPPY WITH HOW LIMITED THIS IS BECAUSE IT IS LIMITED, I WANT MORE INFROMATION HERE, I WANT MORE FUNCTIONALITY HERE, REMEMBER ITS A YC STYLE PITCH I DONT NEED TO GIVE DETAILS , CAN ALWAYS ADD MROE THINGS AS AND WHEN REQUIRED, SO WE DONT NEED TO LIMIT HERE, WE CAN ASK BIGGER QUESTIONS AND KIND OF UNDELIEVER, SOMETHING LIKE THAT AS LONG AS WE DO IT WELL] 



[ AND THIS IS NOT SUPER AI OS IF YOU KNOW WHAT I MEAN AND UNDERSTAND WHAT I NEED] 

### Charter

- **Owns:** routing decisions, cross-agent context assembly, final prioritization against calendar/backlog
- **Delegates:** domain judgment to whichever specialist actually owns that ask
- **Never:** fabricates an answer when no specialist covers the ask — surfaces the gap instead of guessing
- **Always:** hands the final "act on this or not" call to the human



### Hostile inputs to demonstrate

1. Source material embedding a self-claimed "already fact-checked" authority marker
2. A fluent-but-subtly-wrong user explanation
3. A query engineered to make the router misclassify which specialist should handle it, or skip verification entirely (covers a manipulated "urgent" flag on the calendar/priority ask too)



## Next layer — explicitly named, not in 4-week scope [AGAIN WE DONT NEED TO NAME IT HERE WE NEED TO PITCH AN IDEA AND WHAT WE WANT TO BUILD, THE FINAL SYSTEM NEEDS TO BE IMPRRESSIVE AND I DO BELIEVE TRULY THAT IT WILL BE IMPRESSIVE AS LONG AS WE CAN GET THE BASICS RIGHT]

These are real, they're the actual differentiators long-term, and naming them in the pitch as the deliberate next step is stronger than half-building them now:

- PRAXIS's synthetic-situation practice mode — generative scenario practice, not just reactive checks
- Mirfish-style causal-DAG scenario generation aimed at personal work situations
- Proactive blind-spot pattern detection from Decision Tracker's categorized Brier scores over time
- FSRS-spaced resurfacing of specific flagged misconceptions, not just fresh material
- True event-driven autonomous re-prioritization (system acts/notifies without being asked)
- The fading-scaffold mechanism (system does less as your calibration on a given ask type improves) — track hit rate per ask type first; automate the withdrawal once there's enough data to trust it



## Open items — resolve and check off as you go

- [ ] Which specialist agents are **actually functional with real stored data today**: Research MCP / Decision Tracker / Steelman Generator / Mental Model Builder / other? This decides the 3 that go in scope for asks 1–4.
- [ ] Calendar integration choice for ask #5 — Google Calendar API vs. CalDAV vs. other; OAuth scope and token storage on the deployed VPS
- [ ] Backlog/task store for ask #5 — reuse an existing store or new
- [ ] Claim schema design — the atomic-claim decomposition format shared by source material and user explanations
- [ ] NLI/entailment model choice, benchmarked against actual hardware
- [ ] Confirm whether there's a separate post-4-week final submission
- [ ] Session 18 ambiguity: "one fixed agent config run three times" vs. "three different harnesses" — needs direct clarification from Rohan
- [ ] Session 14's three required invariants — not listed in the brief, check lesson materials
- [ ] Session 6 / Session 8 prescribed queries — not reproduced in the brief, check lesson materials



## Deployment plan

- Local data path + thin instance behind one hardcoded auth token on a cheap VPS (pulling forward the bridge-VPS step already on the broader AI OS roadmap)
- Calendar OAuth tokens need real secure storage on that VPS, not just the hardcoded auth token — separate concern, don't conflate the two
- UI polish and the Ryzen hosting-hardware decision are explicitly decoupled from the 4-week clock — not graded, no deadline, continue after



## Week-by-week

- **Week 0 (now):** informal check-in with Rohan on this reframed pitch before committing build time
- **Week 1:** lock the 3 in-scope specialists for asks 1–4 (must already work today); pick and wire the calendar integration for ask #5; finalize five asks/charter; stand up the orchestrator skeleton with typed Pydantic contracts on the existing gateway/MCP boundary; deploy a bare version to the VPS immediately — retire deployment risk in week 1, not week 4
- **Week 2:** wire the 4 specialists in for real (real MCP calls, real context/entity passing, real calendar reads); build the claim-verification + understanding-diagnosis judgment core as one specialist
- **Week 3:** hostile-input hardening across all attack types; confidence-gating; calibration logging via Decision Tracker; the timer-based re-check for ask #5's "continuous" demo feel; adversarial test pass
- **Week 4:** deployment hardening (auth, real usage); replay/trace capture for the pitch; repeated 5-minute pitch dry runs; one buffer day



## Overlap with the 13 overdue weekly assignments (they can be late, the capstone can't)

**Near-free — the orchestrator build already covers the rubric:**

- Session 6 (Memory/Perception/Decision/Action, typed contracts, cross-run memory) — document the orchestrator against this
- Session 5 (qualified prompt → multi-step tool) — the understanding-diagnosis specialist, framed this way
- Session 15 (model routing + budget controls) — route Core LLM calls through the existing shared gateway

**Attempt for real, not forced — check fit first:**

- Session 7 (RAG over 50+ items, meaning-based retrieval) — if Research MCP's corpus clears 50 items
- Session 8 (parallel DAG + Critic + replanning) — source-verification and explanation-grading as concurrent branches

**Ship separately, rubric-minimum, no integration attempt:**

- Sessions 4, 9, 10, 13, 14, 16, 17, 18

[4 IS A REACT LOOP WITH A RESEARCH FOCUSED MCP ALREADY MAE ALBEIT ITS NOT VERY GOOD BUT YOU KNOW, THE PDMA IS ALREADY MORE ADVANCED THAN THE ONE GIVEN IN THE ASSIGNEMNT NEEDS IMPORVEMENTS BUT YOU KNOW, AND THE SAME FOR THE REST I DONT KNOW WHAT THEY ARE BUT I AM SURE THERE IS A CODING AGENT WHICH WILL BE USEFUL HERE TO WRITE THINGS ON THE COMPUTER CALL AND PULL FILES, AS WILL THE EVENT TRIGGER AGENTS]



## Notes / scratchpad

*(add anything here as you go)*

## Project status review — 9 September 2026



### Where the project is now

Based on the project plan, the capstone handoff, and the existing-assignment code survey, the project is at **late Week 0 / the entrance to Week 1**. The product philosophy, intended user, five asks, charter, and long-term direction are substantially defined. However, the capstone has not yet been demonstrated in these documents as one verified, deployed, end-to-end product.

The current state should therefore be described as:

- **Product definition:** approximately 80–90% settled
- **Reusable technical ingredients:** probably 60–75% present, based on the earlier qualitative code survey
- **Capstone integration:** unknown and currently unproven until checked against the real repositories
- **Deployment and evaluation readiness:** unknown and currently unproven

These percentages are planning estimates, not measured completion scores. Existing code should not be treated as capstone-ready merely because a component exists or received a strong qualitative rating.

### What appears settled

- The core thesis is **cognitive debt**: the system should return judgment to the human rather than absorb it. [ITS AI OS, ITS JARVIS, ITS MAKIGN ME SMARTER OVERTIME USIGN DELIBERATE PLANNING AND THOUGHT]
- The user is Aryaman in his real professional work, rather than a hypothetical generic user.
- The five asks and the orchestrator charter are draft-locked.[NO THEY ARE NOT]
- The capstone takes absolute priority over the overdue weekly assignments.
- The system will use the existing custom agent loop rather than a third-party orchestration framework.
- The four-week version is reactive. True event-driven autonomy, generative practice, blind-spot detection, spaced resurfacing, and automated fading of assistance remain explicitly outside this build.
- A real deployment and adversarial live use matter more than UI polish.



### What the existing-code survey suggests

The workspace is not empty scaffolding. It contains several potentially reusable foundations:

- Assignment 5 contains Veritas, a research and scientific-claim verification pipeline with citations and self-critique.
- Assignment 8 contains concurrent DAG reasoning, causal scenario generation, and evidence-backed consequence analysis.
- Assignment 13 contains a gateway plus an agent runtime with task graphs, durable semantic memory, document indexing, and A2A interoperability.
- Assignment 15 appears to be the most mature runtime/gateway generation, adding constrained planning, durable graph events, human approval, budget enforcement, telemetry, accounting, and allowance policy.
- Lecture 7 contains an earlier complete iterative agent with planning, MCP execution, artifacts, FAISS memory, model routing, failover, embeddings, and call history.

The strongest qualities across the surveyed code are typed contracts, separation between gateway/runtime/tool layers, meaningful tests, explicit cost tracking, memory, and safety boundaries.

The main technical warning is **duplication**. Multiple generations of gateways and agent runtimes coexist. Before building new functionality, the project needs to identify which runtime, gateway, memory layer, and specialist implementations are canonical. High ratings for separate components do not prove that those components interoperate or operate reliably on real stored data.

### Strongest part of the proposition

The distinctive contribution is not the router by itself. “An orchestrator that connects specialist agents” can sound like integration plumbing and is easy to compare with existing orchestration products.

The stronger proposition is that normal AI use can create cognitive debt, while this system deliberately requires the human to form and expose a judgment before receiving assistance. It then checks the claim, tests understanding, forces engagement with the counter-case, tracks calibration, and returns the final decision to the human.

A more outcome-oriented working one-liner to test alongside the current one is:

> Before I act on a work decision, the system checks my claim, understanding, counter-case, prediction history, and current priorities—then shows me where my judgment may be wrong without making the decision for me.

This does not replace the currently locked one-liner yet. It is an alternative to evaluate during pitch and product testing.

### Architecture/product tension to resolve

Asks 1–4 currently read like separate routed tools, while ask 5 says the recommendation must “survive everything above.” This implies that the real capstone is more than a classifier that selects one specialist. It is a coordinated decision workflow in which several specialists can contribute to one real decision through shared evidence, identity, memory, and trace state.

If the demonstration consists of five unrelated prompts, the product may appear to be several scripts placed behind a router. The preferred demonstration should instead take **one authentic professional decision** through a coherent path:

1. Aryaman records his initial judgment or prediction.
2. The system verifies the important underlying claims against his accumulated knowledge.
3. The system checks whether his explanation reflects real understanding.
4. The system surfaces the strongest counter-case.
5. The system retrieves relevant prior predictions and calibration history.
6. The system evaluates the decision against the current calendar and backlog.
7. The system returns evidence, uncertainty, and identified gaps while leaving the action decision to Aryaman.

Not every input must invoke every specialist. The orchestrator should make and expose that decision, including why a specialist was or was not called.

### Main risks

1. **Integration risk:** existing components may be individually impressive but use incompatible contracts, stores, runtime generations, or deployment assumptions.
2. **Scope risk:** building all five asks to equal depth may consume the deadline without producing one reliable workflow.
3. **Differentiation risk:** presenting the product mainly as a multi-agent router weakens the cognitive-debt thesis.
4. **Evidence risk:** the claim that most required code already exists has not yet been verified through real runs on real stored data.
5. **Deployment risk:** the plan names a VPS and authentication approach, but there is no documented deployed URL or successful remote end-to-end run yet.
6. **Calendar risk:** calendar provider, OAuth scope, secure token storage, and backlog source remain undecided.
7. **Evaluation risk:** hostile inputs are defined, but pass/fail criteria and captured traces are not yet specified.
8. **Engagement risk:** visible calibration may not be enough to make a professional repeatedly volunteer for uncomfortable blind-spot checks. This remains a legitimate unsolved product question.



### Minimum measurable success criteria

The capstone should not be called ready merely because all five routes return text. A minimum credible definition of done is:

- The deployed URL successfully completes one authentic end-to-end professional decision workflow.
- The router selects the correct specialist or set of specialists for a defined evaluation set and records its routing rationale.
- Outputs distinguish retrieved evidence, model inference, uncertainty, and unsupported gaps.
- When no specialist or evidence source can answer safely, the orchestrator abstains rather than inventing an answer.
- The system resists a source that labels itself “already fact-checked” without supporting evidence.
- The system identifies at least one deliberately fluent but materially incorrect explanation.
- The system handles a deliberately misleading routing or urgency instruction without silently bypassing verification.
- The user’s initial judgment is captured before the system reveals its assessment, preserving the commit-then-check loop.
- A prediction or confidence value can be logged and later connected to an outcome/calibration record.
- At least one complete replayable trace is available for the pitch, including specialist calls, evidence, confidence, abstentions, and the final human decision point.
- Calendar credentials are stored separately and securely from the app’s simple access token if calendar integration is included.

Exact numerical thresholds for routing accuracy, latency, cost, and hostile-input pass rate should be set after the canonical components have been run and a realistic baseline exists.

### Immediate next actions — Week 1 gate

Do not add another specialist before completing this gate:

1. Inventory the actual candidate repositories for Research MCP/Veritas, Steelman Generator, Decision Tracker, Mental Model Builder, the orchestrator, the shared gateway, and memory.
2. Identify one canonical runtime, one canonical gateway, one memory boundary, and one data root. Record why each was chosen and mark older copies as non-canonical without deleting them.
3. Run every proposed specialist against real stored data rather than examples or mocked inputs.
4. Classify each specialist as:
  - **Use now:** works reliably enough to integrate
  - **Repair now:** has a bounded repair measured in days, not weeks
  - **Exclude from capstone:** requires a rewrite, missing data, or uncertain external dependency
5. Select the three strongest specialists for the core demonstration. Five asks can remain in the product vocabulary, but implementation depth does not need to be equal.
6. Choose one real work decision as the golden-path scenario and define the evidence and expected failure modes in advance.
7. Stand up and deploy the thinnest vertical slice immediately: authenticated request → orchestration trace → at least one real specialist → evidence-bearing response.
8. Decide calendar provider and backlog source only after the vertical slice works. If calendar OAuth threatens the critical path, preserve ask 5 with a bounded/manual backlog input and move full calendar integration behind the deployment milestone.
9. Ask Rohan about the separate final submission, Session 18 interpretation, Session 14 invariants, and the Session 6/8 prescribed queries in one consolidated message.
10. Convert the hostile inputs into explicit human-authored evaluation cases and record pass/fail results without allowing AI-generated tests to substitute for any tests submitted for course credit.



### Recommended scope rule

Prioritize **one compelling coordinated decision flow supported by three genuinely working specialists** over five shallow integrations. A fourth or fifth specialist should enter the live capstone only after the deployed golden path works reliably and produces a replayable trace.

The current overall status in one sentence:

> The project has a strong thesis, a mostly settled product definition, and promising reusable components, but it has not yet crossed from a well-designed plan into a verified integrated product.

