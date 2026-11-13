# Capstone MVP: due Sunday 22 Nov 2026, end of day

Status: proposed by Claude on 13 Nov 2026. Nothing here is approved until you settle the conflicts at the bottom. If approved, this replaces the dates and the "frozen" scope in `stages.md` until submission; the interfaces in `interfaces.md` stay as they are.

## The deliverable, in one sentence

A deployed assistant that takes any of my five judgment questions, routes it to the one specialist tool that owns it, answers once, and never obeys an instruction it finds inside what it reads.

## What passing needs

The course rules for your route ask for four things: your own loop with no agent framework, a clear deliverable someone can check, four weeks of real work, and a deployment on EC2 or Hetzner at a URL they can open. The real bar, from the handoff, is the deployed app surviving live and hostile use. Screen design is not marked.

So the MVP is judged on three checks. Each of the five asks, typed at the public URL, reaches the right tool and gives a correct answer. Each of the three hostile inputs is handled. When no tool covers a question, it says so and does not guess.

## The shape: a spine, one deep ask, four thin asks

**The spine** is five small trunk files. `core/llm.py` is the only door to a model (I1). `core/store.py` is one SQLite file that each owner adds its tables to (I2). `core/registry.py` is the list of tools the loop may call (I3). `core/loop.py` is the hand-written loop: read the ask, pick one tool, call it, answer once (I12). `core/web.py` serves `/health` and a token-guarded `/ask` page (I17). The loop comes from the Assignment 6 agent, which is already written, typed and tested.

**The deep ask is ask 2**, "did I understand it, or just recognise the words?" It is the one piece nobody else has and the centre of a learning system. You type an explanation of a card; the tool grades it as wrong, fluent but wrong, partial, correct or complete (I5), says what is missing, and logs a mistake when it is wrong. This gets real depth: your real cards, your real examples, and the fluent-but-wrong hostile input.

**The other four asks are thin on purpose.** Each is the smallest thing that honestly answers its question, behind the interface already written for it, so it can deepen later without changing anything around it.

Ask 1, "is this claim true, and where did I already establish it?" (I18): one model call for the verdict, plus SQLite's built-in text search over your cards and mistakes for the "where". A source's own claim to be fact-checked earns nothing.

Ask 3, "what is the strongest case against my view?" (I19): two model calls in plain Python, one for the strongest counter-case and one for the crux.

Ask 4, "what did I predict, and was I right?" (I20): log a prediction with a probability, resolve it later, and compute the Brier score (a standard measure of how good probability forecasts were). No model call is needed.

Ask 5, "given my calendar and backlog, what now?" (I8, I9): a task table plus a read-only calendar feed link, ranked by one model call. No Google sign-in flow.

## What is cut until after Sunday

Telegram, spaced-repetition scheduling, card generation from notes, the screenshot reader, the scheduler and morning push, Langfuse traces, database backup, and every project under `projects/` that is not named above. Each one already has an interface or a later stage, so cutting it now removes no foundation. The reason for each cut is the same: the three checks above can be shown without it.

## Why this is a foundation and not a throwaway

Every later AI OS module is either a new tool in the registry or a new surface over the loop. Telegram becomes a second surface next to the web page. The reader, steelman depth, the full decision tracker and the knowledge graph each sit behind an interface that already exists. Deleting any leaf leaves the spine working, and `tests/test_structure.py` already enforces that.

## What each assignment gives the capstone

Assignment 6 gives the loop. Assignment 4 gives the tool-boundary pattern. Assignment 7's retrieval is the upgrade path for ask 1's "where" once text search stops being enough. Assignment 15, if its workload is recall grading, is the measurement behind which model grades ask 2. Assignment 18's save-then-score pattern is the shape of the eval runner. Assignments 14 and 16 become the screen and the Telegram surface after submission. Assignments 5, 8, 9, 10, 13 and 17 feed later stages and nothing in the MVP waits on them.

## The days

**Fri 13 to Tue 17 Nov: assignments.** The only capstone work is yours and small: settle the conflicts below, rent the server, and write five real ask-2 examples (card, your answer, the verdict you expect).

**Wed 18: the spine, deployed.** `/health` and `/ask` answer at the public URL, and one fake tool is called end to end through the loop. Deploying first means it cannot fail in the last week.

**Thu 19: ask 2 end to end** on your five examples, plus the fluent-but-wrong hostile input.

**Fri 20: asks 1, 3 and 4**, plus the "already fact-checked" hostile input.

**Sat 21: ask 5, routing across all five**, the misrouting hostile input, and "no tool covers this, so I will not guess".

**Sun 22: no new features.** Dry runs at the public URL, the README, a one-page `DESIGN.md`, a recorded fallback demo, then tag and submit before evening.

## Cut order if a day slips

First, ask 5 drops the calendar and ranks tasks only. Second, ask 3 drops to one call. Third, ask 4 drops resolve and score and keeps the log. Fourth, ask 1 drops the "where" and keeps the verdict. Never cut: the deployment, ask 2, the router, the three hostile inputs.

## What I need from you

Five real ask-2 examples by Tuesday. The eval cases, written by your own hand: about fifteen, including the three hostile inputs, since the course says a test written by Claude or Codex scores zero. I can propose categories, not cases. A server and a domain or address by Wednesday morning. About an hour a day from Wednesday to review each stage on real data.

## Conflicts for you to settle

1. **Scope.** `stages.md` freezes five full stages for an end-of-December date; `Rules.md` sets 22 Nov and allows a minimal restart. Five stages do not fit in five days. This plan assumes the cut above.
2. **Telegram.** Stage 1 is done only after a week of reviewing in Telegram. That cannot happen before Sunday, and graders cannot use a bot that only answers you. This plan assumes the web page is the only surface.
3. **The gateway.** The 3 Nov decision is to finish the gateway, but it has never worked end to end. I propose a half-day limit on Wednesday morning: if one real call is not logged by noon, `core/llm.py` calls the approved any-llm library directly and the gateway goes behind it after submission.
4. **Libraries versus hand-written.** `Rules.md` wants hand-written parts replaced with libraries this week. Before Sunday that earns no marks and risks breaking working code. I propose replacing only what is broken, and doing the rest after submission. The loop stays yours either way, as the course requires.
5. **Who writes the tests.** `Rules.md` asks for minimal input from you; the course wants tests by your own hand. I propose you write the eval cases and Claude and Codex write only the code.
6. **Where it runs.** The course says EC2 or Hetzner; `stages.md` lists Oracle's free tier as a fallback, which the course does not allow. Hetzner's smallest server is a few euros a month. This plan assumes Hetzner.
7. **Assignments before capstone.** The handoff says the capstone takes strict precedence; `Rules.md` puts all thirteen assignments first, leaving five build days. If Tuesday slips, I propose the capstone starts Wednesday regardless and unfinished assignments wait.
8. **What gets submitted.** Still unconfirmed with the instructor: a repo, a video, or only the live URL. Worth asking him this week.
