# EAG V3 Capstone — Project Plan (Consolidated)

Consolidated from the annotated `PROJECT_PLAN.MD` — same decisions, comments merged into prose, repetition removed. Original left untouched.

## North star: why this exists

AI use, done the normal way, is a withdrawal against your own cognition — you offload judgment, it feels free, but the capability atrophies ("cognitive debt"), and you lose agency along with the skill. The fix isn't less AI, it's AI whose job is to keep handing judgment back to you instead of absorbing it. That's the pitch, viewed from an upside-down lens: most AI products make you dumber by being convenient; this one is designed to make you sharper by being inconvenient in exactly the right way.

This is a personal tool shaped around one actual life (yours), not an institutional deployment. Everything in your life should have AI woven through it if you want to be on top of this technology and get the most out of it. Right now that's bounded to this codebase and cloud models; a local AI box is coming, and the same design should extend to it.

What that means concretely:

- **Commit before you're checked.** Form a judgment first, then get checked against it (asks #1–#2). Beyond checking what you commit to, the system should actively hunt for claims that need more nuance, surface gaps you didn't know you had, and show you where you're missing something — including places where you've read something and want to follow it but structurally can't yet.
- **Force engagement with the counter-case**, not a verdict (ask #3). *Open question — not yet designed:* what "force engagement" actually means mechanically (block progress until a response is given? require a written rebuttal? something else) still needs to be decided.
- **Track calibration as a real number.** Decision Tracker's Brier scoring, broken out by category over time, is the mechanism — it turns "am I getting better" from a vibe into a number that moves, and it's what makes proactive blind-spot detection possible ("you're systematically overconfident about X") instead of only reactive correction.
- **Mastery through repetition.** An athlete gets thousands of fast, unambiguous, low-stakes reps at escalating difficulty; a professional almost never does. The mechanism for converting expensive real-world learning-by-mistake into cheap simulated learning-by-mistake is PRAXIS's synthetic-situation practice mode — already built and tested (`AI Code/Accountability Agent`, server name PraxisEngine), currently kept out of 4-week scope by deliberate choice, not because it doesn't exist (see the Next-layer section's correction below) — generating scenarios via the same causal-DAG pattern Mirfish already uses for market knock-on effects — aimed at personal work situations instead of news events. There's more in Mirfish worth mining here than just this one pattern; not yet scoped.
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

**Correction (verified against the actual repos):** the ReAct loop referenced here as "Assignment 4" doesn't exist under that name in `EAG V3 Course` — no such folder, no PDMA hits anywhere in that tree. It's most likely `AI Code/React Loop` (a real hand-built ReAct-style loop — though the Constitution review below recommends demoting it to coursework status rather than using it as capstone substrate). The PDMA implementation "more advanced than the assignment baseline" is most likely **Assignment 10** (`perception.py`/`decision.py`/`action.py`/`flow.py`, plus sandbox/replay/skills/recovery/mcp_server/vector_index modules) — a real, more complete PDMA build than assumed, previously unnamed anywhere in this plan. Re-verify both attributions before citing them again; Assignment 10 in particular is candidate substrate for the coding-agent and event-trigger pieces above.

## Current direction: AI OS Orchestrator (working name: "Judgment Gate," not "CEO-Planner")

The pitch leads with cognitive debt, not with orchestration mechanics — the north star above *is* the thesis, and every section below exists to serve it, not the other way around. "CEO-Planner" undersold that: it reads as a scheduling/management metaphor, when the component's actual job is to intercept the moment you'd normally offload judgment to AI and hand it back to you first. "Judgment Gate" names that function directly and ties straight back to the north star's "commit before you're checked" framing.

**Working one-liner (current):** An orchestrator that takes what I need to figure out and routes it across my own already-built specialist agents — research/verification, understanding-diagnosis, argument stress-testing, calibration, life-priority — through a shared memory layer, not stapled scripts.

**Alternative one-liner (outcome-oriented, evaluate alongside the above):**

> Before I act on a work decision, the system checks my claim, understanding, counter-case, prediction history, and current priorities — then shows me where my judgment may be wrong without making the decision for me.

Important framing: this is mostly already-written code getting a macro-level orchestration pass, not a from-scratch build. It ships the Judgment Gate orchestration layer already on the AI OS roadmap, pulled forward onto a forced deadline — which is a feature, not a compromise: the deadline forces more real progress than would happen otherwise.

The distinctive contribution is **not** the router itself — "an orchestrator that connects specialist agents" reads as integration plumbing and invites comparison to generic orchestration products. The real proposition is that normal AI use creates cognitive debt, and this system deliberately requires you to form and expose a judgment *before* receiving assistance, then checks the claim, tests understanding, forces engagement with the counter-case, tracks calibration, and returns the final call to you.

**Who the person is:** you, at your actual job — not a hypothetical generic new-hire. Easier to defend live since you can speak from what actually happened.

### Five asks — working draft, not locked

These are the current best formulation, not a final spec. There's real appetite to ask bigger here as the AI OS pillar above gets folded in — treat these as expandable, not as a ceiling.

1. Is this claim actually true, and where did I already establish that? → Research MCP / accumulated corpus.
2. Did I actually understand what I just read, or just recognize the vocabulary? → understanding-diagnosis specialist (the genuinely new build).
3. What's the strongest case against my current view on this? → Steelman Generator.
4. What did I predict here before, and was I right? → Decision Tracker.
5. Given my calendar and backlog, what should I actually be doing right now, and does it survive everything above? → life-priority specialist (calendar integration + backlog store); the orchestrator's own gating decision, with the final call handed to the human. Ships **reactive** in 4 weeks — same ask-and-answer pattern as the other four. The "continuous" feel for the pitch comes from re-running the same check on a timer and surfacing what changed, not from a new autonomous architecture. **Substrate already exists and changes the plan:** `AI Code/Personal/Planner and Reminders` is a working AppleScript-based Apple Calendar + Reminders integration (its own MCP server, a daily-scan/reshuffle feature, session memory) — no Google OAuth needed, and no backlog store to build from scratch (Reminders serves that role). This removes the OAuth-risk hedge below, but introduces a different open question: AppleScript only runs on the Mac it automates, while the deployment plan targets a hosted VPS — decide whether ask #5 runs against a local bridge back to that Mac, a synced snapshot, or a scoped-down manual input for the hosted demo, before Week 1 closes.



### Charter

- **Owns:** routing decisions, cross-agent context assembly, final prioritization against calendar/backlog.
- **Delegates:** domain judgment to whichever specialist actually owns that ask.
- **Never:** fabricates an answer when no specialist covers the ask — surfaces the gap instead of guessing.
- **Always:** hands the final "act on this or not" call to the human.
- **Runtime constraint (new):** built as Claude Code + the existing `AI Code/mcp_server` tool surface, not a new hand-rolled agent loop — per an existing internal architecture review (`AI Code/Constitution/AI_OS_REVIEW_2026-07-11.md`) that independently reached "don't build a third loop" after finding two already coexist (`React Loop`, `AI Agent`).



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

**Correction, not yet a scope decision:** PRAXIS (`AI Code/Accountability Agent`, server name PraxisEngine) is not "shelved" as implied above — it's a real, tested ~1100-LOC engine (card ranking, contradiction-graph, evidence retrieval, persisted state). Whether that changes what belongs in the 4-week build, versus staying named-but-deferred here, is a real choice — flag it for a deliberate call rather than quietly pulling it into Week 2/3 scope, which the Recommended scope rule below argues against by default.

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

## Where the project actually is (as of 12 Sept 2026)

Late Week 0 / entrance to Week 1. Product philosophy, intended user, five asks, and charter are a strong draft (not yet locked — see above). The candidate repositories have now actually been surveyed by opening the code, not just the folder names (see below) — that closes part of what was previously "unproven" — but the capstone still hasn't been demonstrated as one verified, deployed, end-to-end product.

- **Product definition:** ~80–90% settled.
- **Reusable technical ingredients:** confirmed present and generally more mature than the original qualitative estimate — Steelman Generator, Decision Tracker, Veritas, and an AppleScript calendar/reminders integration all run against real code paths, not just examples. `ingestion-pipeline`, previously unlisted anywhere in this plan, is a real, actively-committed corpus system.
- **Capstone integration:** the components exist; wiring them together does not yet. Specifically unproven: whether Veritas can query the accumulated corpus rather than only the open web (the `ask_my_data` gap, below); whether Steelman/Decision Tracker/Mirfish can be called from an orchestrator over a real interface (a versioned adapter contract exists in `model_forge` but nothing implements its remote side yet); and which of 8+ gateway generations and 2 hand-built agent runtimes is canonical.
- **Deployment and evaluation readiness:** partially de-risked — `AI OS/gateway` + `AI OS/shell` is an already-deployable, tested, authenticated slice; it has not yet been pointed at a real specialist end-to-end or put on a public URL.

These are planning estimates, not measured scores — existing code isn't capstone-ready just because a component exists or rated well qualitatively.

### What the existing-code survey found

Verified by actually reading entry points, key modules, and tests in `Original Code/AI Code/` and `Original Code/EAG V3 Course/` — not inferred from folder names:

- Assignment 5: Veritas — a research/scientific-claim verification pipeline with citations and self-critique, more mature than a one-line summary suggests: decompose → search → fetch → extract → grade → synthesize → verify → compose, with a citations-integrity checker and an adversarial audit loop that can send itself back for more evidence.
- `EAG V3 Course/veritas copy` is a stale, strictly earlier duplicate of Assignment 5's veritas (diffed directly — missing the citations checker and later hardening). Superseded, not a second candidate; don't cite it going forward.
- Assignment 8 is actually three separate builds, not one: a DAG Agent (Planner/Executor/Critic over equity-comparison queries), **Consequence Radar** (causal-DAG scenario generation over Indian equities — also exists, and is likely duplicated, as a top-level `AI Code/Consequence Radar` folder; needs reconciling before either is picked), and a separate What-If Analyser not yet inspected in depth.
- Assignment 13: gateway (`glc_v3`) + agent runtime (`S13Code-2`) with task graphs, durable provenance-bearing memory, document indexing, and A2A interoperability over both JSON-RPC and gRPC — confirmed; the runtime only talks to the gateway over HTTP, a real separation of concerns.
- Assignment 15 (`glc_v4`): confirmed "v3 plus agent economics" — real per-call cost/billing/allowance logic, not aspirational.
- Lecture 7: confirmed complete iterative agent — 5-stage Memory/Perception/Decision/Action loop, FAISS-indexed retrieval, multi-provider gateway with failover.
- **Assignment 4, as previously cited elsewhere in this plan, doesn't exist under that name** — see the correction in the AI OS pillar section above; it's most likely `AI Code/React Loop` (ReAct) and Assignment 10 (PDMA), not Assignment 4.
- **New — previously absent from this section entirely:**
  - `ingestion-pipeline` (its own git repo, active recent commits) — a working knowledge-graph + vector-store ingestion system (Neo4j + Chroma/Nomic embeddings + gateway-based extraction), with a documented decision trail and a test suite that explicitly forbids live network calls in unit tests. This is very plausibly the actual "accumulated, verified knowledge base" this plan's differentiator claims exists (see "Why the scope changed" above) — it was previously unnamed and untreated as real infrastructure.
  - `AI Code/Database` — the corpus store behind that pipeline (Chroma, a SQLite ledger, Neo4j, raw bronze files). Real data is present.
  - `AI Code/Constitution/AI_OS_REVIEW_2026-07-11.md` — an existing, code-grounded internal architecture review (benchmarked against PAI/LifeOS, OpenClaw, and academic AIOS/MemoryOS work) that independently reached the same "duplication is the top risk" conclusion this plan reached separately, and makes one binding recommendation adopted above: don't build a third hand-rolled agent loop, use Claude Code + the existing MCP server as the runtime.
  - `AI Code/AI OS/gateway` + `AI OS/shell` — an already-deployable, tested FastAPI + React pair (bearer-token auth, `mypy --strict`, generated OpenAPI, real pytest/vitest suites) partially wired to `ingestion-pipeline`. Close to this plan's Week 1 "thinnest vertical slice" target; shouldn't be built from scratch (see Week 1 gate, step 7, below).
  - `AI Code/Accountability Agent` (server name **PraxisEngine**) — PRAXIS's synthetic-situation practice mode, described elsewhere in this plan as "shelved," is **not shelved**. It's a real, tested ~1100-LOC TypeScript engine (card ranking, contradiction-graph, evidence retrieval, schema-constrained LLM calls, persisted state). Factual correction, not yet a scope decision — see the "Next layer" section below.
  - Ask #1's engine (Veritas) and ask #1's corpus (`ingestion-pipeline`/`Database`) both exist but aren't yet connected: retrieval over the corpus is currently exposed only as low-level MCP primitives (`vector_db_search`, `kg_neighbors`, etc.), not a composed query surface — the review above calls the missing piece `ask_my_data(query)` and estimates it at roughly a day of composition work. **This, not "does an engine exist," is ask #1's real remaining risk: can Veritas query the accumulated corpus, or only the open web?**

Strongest qualities across the survey: typed contracts, gateway/runtime/tool layer separation, meaningful tests, explicit cost tracking, memory, safety boundaries.

**Main technical risk: duplication — confirmed at the code level, and larger than previously estimated.** At least 8 distinct LLM-gateway generations exist across `EAG V3 Course` alone (`glc_v1_whatsapp` → three `glc_v2`* variants → a top-level `glc_v2_fixed` → `llm_gatewayV9` → `glc_v3` → `glc_v4`, plus `llm_gatewayV7` in Lecture 7), on top of `AI Code/Final Gateway/llm_gateway` (V1–V7) and a fourth, unrelated system referenced in `Future gateway porting`. Two of these are *not* actually competing for the same slot: `Final Gateway/llm_gateway` (LLM-provider routing) and `AI OS/gateway` (UI/API serving — mounts routers, serves the shell) do different jobs and both may legitimately be needed; don't force one canonical pick between them. Two hand-built agent loops also coexist (`React Loop`, `AI Agent`) — the Constitution review above already recommends demoting both to coursework status rather than building a third. Before building new functionality, identify which runtime, which gateway *per job*, which memory layer, and which specialist implementations are canonical — high individual ratings don't prove these components interoperate or work reliably on real stored data. This is the single largest source of integration risk in the whole plan.

## Single sequenced plan (Week 1 gate → Week 4)

Do not add a specialist, calendar integration, or new ask before Week 1's gate (steps 1–7) is complete.

**Week 1 gate:**

1. ~~Inventory actual candidate repos~~ **Done — see the existing-code survey above.** Research MCP/Veritas → `EAG V3 Course/Assignment 5/veritas`; Steelman Generator → `AI Code/Steelman Generator`; Decision Tracker → `AI Code/Decision Tracker`; Mental Model Builder → `AI Code/Mental Models Creator`; corpus → `ingestion-pipeline` + `AI Code/Database`; orchestrator substrate → `AI Code/mcp_server` + Claude Code (not a new hand-rolled loop); calendar/backlog substrate for ask #5 → `AI Code/Personal/Planner and Reminders` (AppleScript-based, see ask #5 above). Remaining unknowns: whether Steelman/Decision Tracker/Mirfish can actually be called from the orchestrator over a real interface (step 3 note below), and whether Veritas can query the accumulated corpus rather than only the open web (the `ask_my_data` gap above).
2. Pick one canonical runtime, one canonical gateway **per job** (LLM-provider routing vs. UI/API serving are different jobs, per the duplication note above — don't force one winner across both), one memory boundary, one data root. Do this from per-repo `git log` commit dates, not file mtimes — confirmed unreliable in this tree (a folder copy or a `uv sync` re-lock can bump mtime without real changes; e.g. `glc_v3`'s mtime reads as the newest file in the whole tree, which is almost certainly an artifact of being recently opened, not recently built). Record why; mark older copies non-canonical without deleting them. Runtime default: Claude Code + `AI Code/mcp_server`, per the Constitution review, unless there's a specific reason `React Loop` or `AI Agent` is actually needed.
3. Run every proposed specialist against real stored data — not examples, not mocks. Note going in: `AI Code/Mental Models Creator`'s `model_forge/adapters.py` already defines a versioned JSON-envelope contract (`model-forge.adapter/v1`) for calling Steelman/Mirfish/Decision Tracker over HTTP, with local heuristic fallbacks when no endpoint is set — a real, useful precedent for the orchestrator's integration shape, but **not yet live wiring**: none of the three specialists currently exposes an HTTP endpoint matching that contract (Steelman and Decision Tracker are Streamlit/CLI apps with their own separate MCP servers today). Building that endpoint — or having the orchestrator call the specialists' existing MCP servers directly instead — is real Week 1/2 work, not something already done.
4. Classify each specialist: **use now** (works reliably enough to integrate) / **repair now** (bounded, days not weeks) / **exclude from capstone** (needs a rewrite, missing data, or an uncertain external dependency). First-pass read from the survey above, to confirm against real data rather than take as final: Steelman Generator and Decision Tracker look **use-now**; Mirfish needs a new domain pack for personal-work scenarios instead of macro/equities (**repair-now**); Veritas is **use-now** as a verification engine but **repair-now** on corpus connectivity (the `ask_my_data` gap).
5. Select the three strongest specialists for the core demonstration. Five asks can stay in the product vocabulary; implementation depth doesn't need to match.
6. Choose one real work decision as the golden-path scenario; define expected evidence and failure modes in advance.
7. Deploy the existing vertical slice rather than standing a new one up: `AI Code/AI OS/gateway` + `AI OS/shell` is already an authenticated (bearer-token), tested FastAPI + React pair partially wired to `ingestion-pipeline`. Extend it to produce an orchestration trace → at least one real specialist → evidence-bearing response, and get it on a real URL. Retire deployment risk in Week 1, not Week 4.

**Week 1 (remaining):** finalize the five asks/charter against the gate's findings; wire ask #5 against the existing AppleScript calendar/reminders integration (`Personal/Planner and Reminders`) rather than building new OAuth calendar access — resolve the local-Mac-vs-hosted-VPS bridging question first (see ask #5 above); if that bridge threatens the critical path, ship ask 5 with a bounded/manual backlog input for the hosted demo and keep the real AppleScript integration for local use; typed Pydantic contracts on the existing gateway/MCP boundary.

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

- Extend the existing `AI Code/AI OS/gateway` + `AI OS/shell` (already bearer-token-authed, tested FastAPI + React) rather than standing up a new thin instance from scratch; get it deployed to a real VPS URL (pulling forward the bridge-VPS step already on the broader AI OS roadmap).
- Ask #5's calendar/reminders integration is AppleScript-based (`Personal/Planner and Reminders`), not OAuth — it only runs on the Mac it's automating. Decide the local-bridge-vs-hosted-demo approach here (see ask #5 above) before assuming a VPS-only deployment covers all five asks. If a Google/OAuth calendar path is added later instead, its tokens need separate secure storage from the app's bearer token — don't conflate the two.
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

- Sessions 4, 9, 10, 13, 14, 16, 17, 18. (Session 4's ReAct/research-MCP baseline and its PDMA — re-attributed to `AI Code/React Loop` and Assignment 10 respectively, see the AI OS pillar above — are already ahead of the assignment spec. A coding agent for computer-use/file operations, and the event-trigger agents, are likely useful substrate across several of these; not yet mapped one-to-one.)



## Recommended scope rule

Prioritize **one compelling coordinated decision flow supported by three genuinely working specialists** over five shallow integrations. A fourth or fifth specialist enters the live capstone only after the deployed golden path works reliably and produces a replayable trace.

## Status, one sentence

> The project has a strong thesis, a mostly settled product definition, and promising reusable components, but it has not yet crossed from a well-designed plan into a verified integrated product.



## Notes / scratchpad

*(add anything here as you go)*