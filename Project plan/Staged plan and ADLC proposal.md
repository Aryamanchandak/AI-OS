# AI OS: staged plan, one-stop plan page, and a faster build loop

**Superseded 2026-11-03 by `plan/` (stages, interfaces, decisions). Kept for its reasoning only.**

Written 2026-11-02. This is a proposal for you to comment on. Nothing has been changed in the plan page or the code.

**Update, same day.** Your answers are recorded in `plan/DECISIONS.md`. The plans now live as Markdown files in `plan/`: stages, interfaces, and one file per node, with the structure in each file's header. Read "plan.json" below as that folder.

## Decisions I need from you first

**1. Is the capstone still live, and when is it due?** The handoff file (9 Sep) gave it a hard four-week deadline, which would have passed by now. The plan page still says "swap to LangGraph once the handmade version is tagged for submission". If the capstone is still live, anything it needs by its date can't be delayed, and Stage 4 below moves up.

**2. Freeze the gateway, and use `simple_llm` for the first stages.** This touches the trunk, so it needs your OK. The gateway has about ten commits of shrinking and 182 passing tests, but it has still never served one real request (`gateway/docs/plans/README.md`). Stage 1 needs exactly one cheap grading call. `gateway/simple_llm/client.py` is a 114-line direct client that has unit tests but no recorded live call yet, so the first bolt of Stage 0 proves one live call through it. My proposal is to put it behind one adapter file and leave the gateway untouched until a stage genuinely needs shared budgets. The other trigger is Graphiti needing one OpenAI-compatible endpoint, meaning a URL that speaks the same request format as OpenAI's API, so libraries built for OpenAI can point at it.

**3. Let Claude and Codex build in parallel.** This breaks your rule "never parallelise anything without a measured bottleneck". My case that the bottleneck is now measured: weeks of trunk work, and nothing in daily use. Parallel here means each agent owns different files. The two never edit the same file.

**4. Outline every stage, but detail only the next one.** Your rule is "plan only the next step". You also asked for plans for each stage. I suggest this reading: every stage gets its nodes, its connections and a one-line "done when". Only the active stage gets a full plan. Confirm, or tell me which way you want it.

**5. Review once per stage, on a branch.** A branch is a separate line of commits that doesn't touch `main` until you merge it. Bolts (small build cycles, defined below) would commit to a stage branch, and each commit stays small. You would review them in one sitting at the end of the stage, with Codex's review notes attached, before anything merges. I'd run the git commands myself: `git switch -c stage-1` creates the branch and moves onto it. At the end, `git switch main` then `git merge stage-1` brings the reviewed work into `main`. That keeps your one real checkpoint but stops you being the brake on every step. The alternative is to keep reviewing every commit.

**6. Langfuse: Cloud or self-hosted?** The plan page says Cloud. `gateway/DECISIONS.md` (19 Oct) says self-hosted. Either way, I propose delaying it to Stage 4. Until then, the adapter logs one row per model call to the store.

**7. The uncommitted Graphiti-readiness work in `gateway/`.** It's 22 modified files plus new docs. Should I commit it as it is, or park it on a branch? Either way it sits outside every early stage.

**8. Is `interview-coach` part of the AI OS?** It isn't on the plan page at all. It does something Stage 1 also needs: it calls Claude directly through its own client in `interview-coach/llm.py` to "generate a question, grade an answer". If it belongs to the AI OS, that's a duplicate model path, and its grading prompt is a candidate to reuse in Stage 1. If it's a separate project, it stays off the page and keeps its own client.

**9. New dependencies for Stage 1.** The new ones are python-telegram-bot (the bot) and py-fsrs (card scheduling). Both are already named on the plan page, but your rules say to ask before adding them. Each would sit behind one adapter file and get an entry in DEPENDENCIES.md. I'd keep the plan file as JSON (`plan/plan.json`) so the page needs no YAML library.

## What I found

The plan page already holds more of your idea than you might think. Its Stages tab has a dependency graph per stage. Each node has a box for your notes ("seed") and a plan. A button copies a whole stage out as Markdown. The page saves itself back to its published link. The live version and your local file are identical, and no node has notes or a plan written yet. So this is an extension of what exists, not a redesign.

There are two gaps that block what you asked for.

The first gap is that **dependencies stop at the stage edge**. The code (`renderStages`) only keeps dependencies between nodes inside the same stage. So when a Stage 1 interface changes, nothing on the page can tell you which Stage 3 nodes rely on it. Making that visible is the job of "update all the stages when we deviate".

The second gap is that **the copied stage isn't enough for a coding agent**. The export includes the goal, kind, needs and notes. It doesn't include the repo path, the test path, the neighbours' interfaces, your done-when examples, who builds what, or what's deliberately delayed.

The page has also drifted from the repo already, which is the problem you're describing:

- **Gateway.** The page shows it as "built, level 2", with FastAPI, httpx and LiteLLM as a reference. The repo uses any-llm, OpenTelemetry and tenacity. The gateway has never been proven live and its deployment is deferred.
- **Langfuse.** The page and DECISIONS.md disagree on Cloud versus self-hosted (decision 6).
- **Graphiti.** The page says Graphiti waits. Graphiti-readiness work is sitting uncommitted in the gateway.
- **interview-coach.** It's missing from the page entirely.
- **Context files.** The page marks "CLAUDE.md and AGENTS.md" as built at level 2. The repo has neither at the top level. The only CLAUDE.md is inside `Original Code/`.

None of this is anyone's fault. Two places hold plans, nothing checks them against each other, and so they drift.

## The staging rule

A node or feature goes into a stage only if that stage's done-when can't be demonstrated without it. Everything else is delayed, and the delayed item is written down with its reason, so delaying it is a decision rather than something forgotten. Stages follow dependency order, not importance: whatever later stages build on comes first.

Your examples are the spec. Each stage's done-when is two or three real examples with known answers, written by you. Those become the first tests, and the stage is done when they pass on real data and you've used it. I've left those examples blank below on purpose, because they're yours to write.

## The stages

The core of everything is the same four pieces whatever ships first: a store, one model adapter, the tool registry and the chat. Stage 0 builds only their contracts, so that every later stage, and both coding agents, can build against them. A contract here is the agreed shape of what passes between two parts: the function name, what goes in and what comes out.

Node names below use the plan page's IDs in brackets, so each one maps to a node on the page. There is one new node, the model adapter `[llm]`. It stands in for `[gateway]` until a later stage brings the gateway back.

**Stage 0: Spine (one or two bolts).**

Nodes:
- **Store `[eventlog]`:** an SQLite schema for cards, reviews, mistakes and events.
- **Model adapter `[llm]`:** `llm.py` wraps `simple_llm` and writes one row per call to the store.
- **Registry `[orch]`, registry part only:** the `@tool` decorator with typed inputs and outputs.

Connections:
- `llm` writes one row per call to `eventlog`.
- Every tool in every later stage registers with `orch`.

Done when: a fake tool registers and gets called, and one real grading call lands as a row in the store. A fake is a stand-in that returns a fixed answer, so one part can be built and tested before the real part it depends on exists.

Delayed:
- the gateway
- Langfuse
- Litestream (a tool that continuously backs up an SQLite file)
- the VPS

**Stage 1: CFA review loop in Telegram, on the laptop.**

Nodes:
- **Telegram bot `[telegram]`:** text answers. It uses long polling, which means the bot asks Telegram for new messages, so no public URL is needed yet.
- **Learning system `[learnsys]`:** cards loaded from a file you write, py-fsrs scheduling, one grading call per concept card, buttons for formula cards, and wrong answers into the mistake log.
- **Grading eval `[evals]`:** your cases (right, wrong, half-right, and fluent but wrong).

Connections:
- `telegram` calls `learnsys` only through `orch`.
- `learnsys` calls the model only through `llm`.
- `learnsys` reads and writes cards, reviews and mistakes in `eventlog`.
- `evals` runs `learnsys`'s grading call against your cases.

Done when: [YOUR EXAMPLES: three real cards, your answer to each, and the grade you expect].

Delayed:
- voice answers
- formula images
- generating cards from your notes
- the screenshot-to-mistake path
- Langfuse

**Stage 2: Feed the learning loop from real input (outline).**

Nodes: `[reader]` (mistake path only) and `[learnsys]` (card generation and formula images).

Connections:
- `reader` calls the vision model through `llm`.
- `reader` creates mistake cards through a `learnsys` tool registered in `orch`.

Done when: [YOUR EXAMPLES].

**Stage 3: Always on, plus Tasks (outline).**

Nodes: `[host]`, `[todo]` and `[eventlog]` (the tasks table and backup).

Connections:
- `todo` registers its tools in `orch` (the Stage 0 registry).
- `todo` stores tasks in `eventlog`.
- The 8am push calls `learnsys` tools through `orch`.
- `telegram` moves onto `host`.

Done when: [YOUR EXAMPLES].

**Stage 4: Assistant and traces (outline; the capstone shape).**

Nodes: `[orch]` (the assistant part), `[trace]` and `[evals]` (running in CI, meaning automatically on every push).

Connections:
- The assistant calls `learnsys` and `todo` tools through `orch`.
- `llm` sends traces to `trace`.

Done when: [YOUR EXAMPLES; the page's current one is "a free-form question uses tools from Learning and Tasks and shows up in Langfuse"].

**Stage 5: The outside world (outline).**

Nodes: `[bridge]`, `[instinct]`, `[claude]` and `[chatgpt]`.

Connections:
- `bridge` registers in `orch`.
- External results come back as events in `eventlog` and land on `todo` lists.
- Claude's to-do connector calls `todo` tools through `orch`.

Done when: [YOUR EXAMPLES].

**Later, names only:**
- the memory substrate and Graphiti (it enters when a stage needs retrieval over your reading, which is the Think tier)
- the Think tier
- Run life
- Extend
- the maintainer loop
- the laptop worker

The gateway comes back when two or more callers need shared budgets, or when Graphiti needs one OpenAI-compatible endpoint.

## How the plan page changes

The aim is one page that holds every piece of context, including what's delayed and why. Every change below is an extension of the existing data, not a new app.

**Connections become real.** Today each node has an untyped "with" list, and stage dependencies are stage-local. Both get replaced by one list of connections across all stages. Each connection says what flows along it, for example "grade(card, answer) returns Grade", and names the file that defines that contract. Once the page has that list, it can trace a change forward: change a Stage 0 contract and every node downstream, in any stage, lights up as affected.

**Each stage gains four things:**
- your done-when examples
- the delayed list, with reasons
- a status (outline, detailed, active or done)
- who builds and who reviews each node

**Each node gains these fields:**
- repo path
- test path
- a line budget
- the date it was last verified, with the test command
- the DECISIONS.md lines that apply to it

**Changes are tracked without a second log.** Each deviation from plan is one line in DECISIONS.md, as your rules already require. The plan file stores only that line's date, the node IDs it touches, and whether the affected stages have been re-synced. Any stage with an un-synced change shows a banner.

**The copy button becomes a build brief.** It keeps today's content and adds the stage goal, your examples, the node's plan, its neighbours' contracts, the file paths, the delayed list and the rules. There are two variants, one for Claude and one for Codex. They're identical apart from the "your role" line, so both agents start from the same context.

**A "Now" strip at the top.** It shows the active stage, the next bolt, and the only things waiting on you: examples to write, trunk approvals and the stage review.

**Fixes for the drift above:** the gateway node, the Langfuse node, Graphiti, the context files, and interview-coach.

**One direction of flow, so it can't drift again.** The repo holds the plan as `plan/plan.json`: nodes, connections, stages, statuses and paths. That's the source of truth, because Claude and Codex read files and a test can check them. The page is a view of that file, plus an inbox for your notes. You write seeds and examples on the page and press Save as you do now. At each stage start, Claude reads the page, merges your notes into `plan.json`, commits, and republishes the page from the file. Facts about the code (paths, statuses, verified dates) only ever flow from the repo to the page. Each field has exactly one writer.

## How the build loop changes (ADLC, adapted)

"ADLC" means two different things, and I'm borrowing from both.

AWS's AI-Driven Development Lifecycle is about the build loop. Its idea is that AI plans, asks questions and implements, while humans make the critical decisions at defined points. Work happens in "bolts", cycles of hours or days rather than sprints. All context lives in the repo, so any session can pick it up. I'm not borrowing its group review sessions ("mob elaboration"). You work alone, and your one checkpoint is the final review.

The Agent Development Lifecycle (Salesforce, Glean, HoneyHive and others) is about the agents themselves. The parts I'm borrowing:
- evals are the spec, written before the build
- every model-calling file has an eval file
- a change that lowers the eval score doesn't merge
- real failures become eval cases before they're fixed (already your level 4)

From spec-driven development (GitHub Spec Kit) I'm copying the pattern, not installing the tool, since that would be a new dependency. The pattern is: a constitution, then spec, plan, tasks, implement, and a converge check. Your CLAUDE.md already is the constitution.

Here's what a stage looks like in practice:

1. You write the done-when examples on the page. That's about ten minutes.
2. Claude turns them into tests and writes the stage's contracts as types plus fakes. Each node now has something to build against.
3. Each node gets one builder and one reviewer, from different models, and they never edit the same files. For example, in Stage 1 Codex builds the Telegram bot against fake Learning tools, while Claude builds Learning and the grading eval. Then each reviews the other's work. A second model catches blind spots that self-review misses.
4. One integration bolt wires the real pieces together and runs your examples on real data.
5. The drift check runs. Claude updates `plan.json`, republishes the page, and you review the stage branch.

That leaves you three touchpoints:
- examples at stage start
- approval for trunk or contract changes
- the stage review

Everything between them runs without waiting on you.

**Keeping stages aligned is a test, not a habit.** A small check (one pytest file under `plan/`) fails if:
- a node's path is missing
- one component imports another without a connection in the plan
- a stage marked done has failing tests
- a change log entry hasn't been re-synced

It runs on every commit, so a deviation can't pass quietly. Re-syncing stays cheap because only the next stage is detailed. Later stages are outlines, so a change usually means editing a line or two.

**Rules for staying lean:**
- Only one stage is active at a time. Anything outside it is frozen.
- Each node has a line budget. Going over means stop and triage, as your rules already say.
- Before writing a function, the builder checks the registry and `plan.json` for an existing tool.
- The reviewer's checklist leads with two questions: does this duplicate something, and does a library already do it?

The gateway is the warning case here. It got trunk polish before any slice used it.

**Both agents follow the same rules.** Codex reads `AGENTS.md`, not `CLAUDE.md`. Your rules sit in your private `~/.claude/CLAUDE.md`, so Codex never sees them. My proposal is one project-level `AGENTS.md` with the build rules, which the repo's `CLAUDE.md` imports. Then both agents read the same text.

## What I'd do next, once you've answered the decisions

1. Draft `plan/plan.json` from the page's current data, with the drift fixed and Stages 0 and 1 in the new shape.
2. Extend the page as described.
3. Add the drift check.
4. Write the Stage 0 plan file.

Each is its own commit. Stage 0 waits for your done-when examples and the OK on decision 2.

## Sources

- [AWS: AI-Driven Development Life Cycle](https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle)
- [github/spec-kit](https://github.com/github/spec-kit)
- [Glean: Agent development lifecycle](https://docs.glean.com/agents/agent-development-lifecycle/adlc)
- [HoneyHive: The Agent Development Lifecycle](https://www.honeyhive.ai/blog/the-agent-development-lifecycle)
- [Salesforce: building agents playbook](https://www.salesforce.com/news/stories/applied-ai-building-agents-playbook/)
- [LangWatch: The Agent Development Lifecycle](https://langwatch.ai/blog/the-agent-development-lifecycle-why-shipping-is-the-easy-part)
- [Claude Code and Codex review workflow](https://knightli.com/en/2026/07/10/claude-code-codex-code-review-workflow/)
- [Codex inside Claude Code: two agents, one repo](https://www.datanovia.com/blog/codex-inside-claude-code.html)
