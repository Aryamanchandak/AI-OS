# Stages

**How a stage is built.** A node joins a stage only if the stage's done-when can't be shown without it. Anything else is delayed, with its reason written down. Stages run in dependency order. Only the next stage is detailed; the later ones are outlines.

Node IDs match the plan page (`AI OS plan.html`), which splits three of them: `store` and `events` are parts of `eventlog`; `registry`, `scheduler` and `assistant` are parts of `orch`; `evalgrade` and `evalsci` are parts of `evals`. Interfaces (I1–I20) are defined in `interfaces.md`. Each node's plan is in `nodes/<id>.md`.

## Code baseline — checked 13 Nov 2026

Existing source is not proof of a working AI OS connection. No live runs were performed for this plan update. The root `core/`, `leaves/`, `tests/contracts/` and `tests/fakes/` currently contain only package markers; the planned integration is not implemented.

**Gateway:** `gateway/src/gateway/` contains the API, service, providers and ledger, with tests under `gateway/tests/`. Keep it. The grading profile and `core/llm.py` are missing; real-call acceptance remains unverified. The gateway-only path is settled.

**Learning:** `projects/learning/learning-system/src/study_system/core/study_core.py` already implements generation, due-card retrieval, ratings and practice. Storage and scheduling code exist beside it. The node plan explicitly retains only selected designs and replaces the scheduler with py-fsrs; this is a deliberate adaptation, not an empty starting point. Before implementation, compare existing tests and table layouts against I4/I5 and preserve the useful behaviour covered by those tests. The Telegram connection and new mistake/grading flow remain to be built.

**Judgment:** `projects/reasoning/decision-tracker/src/decision_tracker/` contains service, store and scoring code; `projects/reasoning/steelman-generator/src/steelman/` contains a pipeline and evaluation code. Both have tests. They are implementation candidates, not merely specifications, but neither is connected through the new root leaves. Review their tests and dependencies when Stage 4 enters; do not assume a rewrite or claim they work end to end.

**Other existing projects:** capture, ingestion, the platform shell and life tools live under `projects/`. They remain reference or side-project implementations under the current scope; their existence does not establish capstone integration. Local untracked `ingestion/` and `workshop/` folders are not treated as approved architecture.

**Next task:** establish the existing gateway baseline using its offline tests, then exercise an existing real-call golden case and verify its ledger row. Record actual results before adding the grading profile/case. Implement I1 only after that baseline is understood. Approval for this plan update does not authorize trunk code changes or paid calls. Stage 0 is incomplete until all its done-when checks pass; later stages remain outlines.

## Capstone scope (frozen until submission, end Dec / Jan)

The submission is the learning-centred system, deployed at a public URL, answering all five asks through one hand-written orchestrator. Nothing outside this map gets built before submission.

- Ask 1, "is this claim true, and where did I already establish it?": `claimcheck`, Stage 4 (I18).
- Ask 2, "did I understand it, or just recognise the words?": `learnsys` recall grading, Stage 1 (I5).
- Ask 3, "what's the strongest case against my view?": `steelman`, Stage 4 (I19).
- Ask 4, "what did I predict before, and was I right?": `decision`, Stage 4 (I20).
- Ask 5, "given my calendar and backlog, what now?": `todo`, Stage 3 (I8, I9).
- The orchestrator that routes across all five: `orch` assistant part, Stage 5 (I12).
- Hostile input 1, a source claiming it's "already fact-checked": the `claimcheck` evals, Stage 4.
- Hostile input 2, a fluent but wrong explanation: the grading evals, Stage 1.
- Hostile input 3, a query built to misroute or skip verification: the assistant evals, Stage 5.
- Public URL and always-on: `host`, Stage 3.

**Your time.** The course wants the eval cases written by you, including the three hostile inputs. Expect writing those cases, plus the done-when examples at each stage start, to be your main cost. Claude can propose categories, not the cases.

## Stage 0: Spine (detailed)

**Nodes:**
- `gateway` (I1)
- `eventlog` (I2)
- `orch`, registry part only (I3)

**Connections:**
- `core/llm.py` calls the gateway.
- Every model call is logged: in the gateway ledger.
- Every later tool registers through I3.
- Every later table is migrated through I2.

- `host`, bare deploy only (I17)

**Done when:**
- One real grading-profile call goes through I1 (`core/llm.py` → the gateway) and is logged in the ledger. This is golden case #1.
- A fake tool registers and gets called.
- Two owners migrate tables into one store.
- `/health` answers at the public URL, and nothing there can spend money.

**Order:** five bites, one plan file each in `stage-0/`.
1. `stage-0/1-gateway-end-to-end.md`
2. `stage-0/2-store.md`, then `3-registry.md`; sequential unless a measured bottleneck justifies parallel work
3. `stage-0/4-llm-client.md` (needs 1 and 2)
4. `stage-0/5-deploy-health.md` (needs 1 and Open #7)

**Delayed:** embeddings, Langfuse, Litestream, and the bot and scheduler on the VPS (Stage 3).

## Stage 1: CFA review loop in Telegram, on the laptop (detailed)

**Nodes:**
- `learnsys` (provides I4 and I5; uses I1, I2 and I3)
- `telegram` (uses I3 and I4)

**Connections:**
- `telegram` calls I4 through I3.
- `learnsys` calls the model only through I1 and keeps its tables through I2.

**Done when:** the four examples in `nodes/learnsys.md` pass end to end from your phone, and you've reviewed in Telegram for a week. Assumed.

**Contracts added here:** I7 (buttons) and I14 (eval file shape).

**Order:** six bites, one plan file each in `stage-1/`. Stage 0 must be done first.
1. `stage-1/1-contracts-and-fakes.md`
2. `stage-1/2-learning-store.md`, then `3-grade.md`, then `4-learning-tools.md` (Claude)
3. `stage-1/5-telegram-bot.md` (Codex), in parallel with 2–4
4. `stage-1/6-integration.md`

**Delayed:** card generation, screenshot-to-mistake, formula images, voice answers, Langfuse.

## Stage 2: Feed the learning loop from real input (outline)

**Nodes:**
- `reader`, mistake path only: wrap the existing Grabber vision step.
- `learnsys`, adding card generation (I6) and formula images.

**Connections:**
- `reader` uses I1 (vision profile).
- `reader` creates pending mistake cards through I6.

**Done when (assumed):**
- A question-bank screenshot becomes a tagged mistake card.
- A page of your CFA notes becomes cards you approve in Telegram.

## Stage 3: Always on, plus Tasks (outline)

**Nodes:** `host`, `todo`, the scheduler (`orch` grows), and `eventlog` (events table and Litestream backup).

**Connections:**
- `todo` registers I8 through I3 and keeps its tables through I2.
- The scheduler (I10) runs only registry tools.
- The bot, gateway and scheduler move onto `host` (I17). `host` already exists as Stage 0's bare `/health` deploy.

**Done when (assumed):**
- You add a task by text from your phone.
- "What now?" answers from your calendar and tasks.
- The 8am review push arrives with the laptop shut.
- The bot answers through the VPS.

## Stage 4: Judgment (outline; asks 1, 3 and 4)

**Nodes:**
- `claimcheck` (new; replaces the retired Research MCP and the orphaned `verify_claim` calls).
- `steelman`, cut to the fewest fixed steps that give a strongest case and a crux. Its nine-stage spec is trimmed when this stage is detailed.
- `decision`: log, resolve and Brier scoring; the Watcher only emits `falsifier_hit`.

**Connections:**
- All three call the model only through I1 and register through I3.
- `claimcheck` searches `learnsys` cards and mistakes through a learning tool, never its tables.
- `decision` keeps its log through I2. The source ledger and author record become views of its one scoring module.

**Done when (assumed):**
- A claim from your reading comes back with a verdict, and links to a card or mistake where you met it before.
- A source saying "already fact-checked" gets no credit for saying so.
- A position you hold comes back with its strongest counter-case and the crux.
- A decision logged with a probability is later resolved and scored.

## Stage 5: Assistant, traces and hardening (outline; the submission)

**Nodes:** `orch` assistant part (I12), `trace` (I13), and `evals` running in CI.

**Connections:**
- The assistant reads `list_tools()` and calls all five asks' tools through I3.
- The gateway's OpenTelemetry export goes to Langfuse.

**Done when (assumed):**
- Each of the five asks, typed freely from your phone, reaches the right tool and answers correctly.
- The run shows as a readable trace.
- The three hostile inputs are handled, and their eval cases pass in CI.
- The app is reachable at its public URL.

Then the code is tagged and submitted.

## After submission (frozen out; names only)

- **The outside world:** bridge, Instinct, the to-do connector, and Claude or ChatGPT adding to-dos (I15, I16).
- **Full Capture:** Readwise, the extension, chat exports; Marginal M3.
- **The memory substrate and Graphiti.** Gateway embeddings come back with it.
- **The LangGraph swap.** Only if the hand-written loop shows a gap you can name.
- **The rest of the Think tier:** Model Forge, PRAXIS, Mirfish (one shared causal-graph library).
- **Run life**, **Extend**, the **maintainer loop** and the **laptop worker**.

## Open (flagged for you to settle)

1. **Gateway path.** Settled 3 Nov: finish the gateway.
2. **Ask 1, "where did I establish it"** (blocks Stage 4). The cheap option is SQLite's built-in full-text search over your cards and mistakes, with no new dependency. The other is to pull Graphiti forward, which breaks the freeze. Assumed: full-text search.
3. **Ask 1, web search** (blocks Stage 4). Whether the gateway can pass a provider's web-search tool through (any-llm 1.29.0) is unverified. If it can't, the "is it true" half answers from model knowledge only. Check before Stage 4 is detailed.
4. **"Hardened" isn't immune** (shapes Stage 4 evals). Delegating to Claude or GPT moves the injection risk to them but doesn't remove it. What comes back is still treated as data, and hostile input 1 still needs your eval cases.
5. **Is Stage 2 inside the freeze?** (blocks Stage 2) I kept it in because the capstone is learning-centred. Cutting it saves a stage.
6. **Offload moves after submission** (nothing blocked; confirm). The external half of Tier 1 (bridge, Instinct, connectors) was "special priority"; under the freeze it waits. Tasks itself stays in Stage 3.
7. **VPS cost** (blocks Stage 0 bite 5, since the deploy moved there). Hetzner is about €10 a month. That conflicts with "no new subscriptions" and with the handoff's "~$2/month". Oracle Always Free is the fallback. Your call before Stage 3.
8. **CFA timing** (affects Stage 1 now). Stage 1's done-when is "reviewed in Telegram for a week". If the exam is mid-November, either that week falls before it, or the done-when changes to the next deck.
9. **How graders reach it** (blocks Stage 3/5). The bot ignores every chat but yours, so a "public URL" with Telegram as the only surface is unusable by anyone else. Options: a token-guarded web `/ask` page (the handoff's plan), or a second demo bot on demo data.
10. **Deploy in week 1.** Settled 3 Nov: "`/health` answers at the public URL" joins Stage 0 (bite 5).
11. **Dates and a cut line** (affects every stage). No stage has a date. Proposal: date stages backwards from the Session 20 pitch; cut order if late is Stage 2, then Steelman down to two calls.
12. **Pitch and demo prep** (no stage owns it). The 5-minute pitch, one hostile input live, a replayable trace, dry runs and a recorded fallback. Proposal: a short "Submit" stage after Stage 5.
13. **Course questions for Rohan** (may add requirements). Separate final submission or video? Session 14's three invariants? Session 18's ambiguity?
14. **Charter evals** (shapes Stage 5 evals). "No tool covers it → say so, don't guess", "the final call is yours", a faked "urgent" flag on ask 5, and "what now?" checking open decisions and claims have no cases yet.
15. **Post-exam deck and the seed deck** (affects Stage 1). If the CFA exam is mid-November, which deck does the demo run on? And who writes Stage 1's first cards, since generation only arrives in Stage 2?
