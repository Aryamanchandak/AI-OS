# Capstone MVP: due Sunday 22 Nov 2026, end of day

**Moved 15 Nov 2026:** the live copy of this file is in `~/Documents/Personal AI/plan/` (repo `personal-ai`). This copy is history; do not edit it.

## Status

Version 4, 14 Nov 2026, updated after the AI OS review (`plan/ai-os-review.md`). You approved version 2 and asked for the later updates the same day; four items at the bottom are still open. This replaces the dates and the "frozen" scope in `stages.md` until submission.

The main change from version 1: the five asks now come from your pitch deck, and the plan is built around one learning loop. The prediction and calendar asks are gone. Version 3 adds the charter and playbooks the course expects, a higher test count, the questioner by name, and steelman as a stretch. Version 4 makes the store the start of your lifelong record and names what follows after Sunday.

A copy you can comment on is at https://claude.ai/artifact/4mBVSLMM3w6fT3wZsdGGZp. This file is the source of truth.

## The deliverable, in one sentence

A deployed learning system that takes in what I read, turns it into flashcards and questions, grades my own-words explanations against the source, and tells me what to re-check before I act on it.

## The problem it solves

An equity analyst reads several documents a day, re-reads them and hopes it stuck. Then they act on something they only think they understood, and a wrong call costs money. That is the person and the cost on slide 2 of your pitch.

A chatbot over stored notes does not fix that; it only answers questions. This system tests you. It checks whether you understood the source or only recognised its vocabulary, and it never lets fluent wording or a source's own claim of authority count as proof.

## The five asks, from your pitch

These are the five asks on slide 3 of your pitch, each with the smallest tool that honestly answers it.

**Ask 1, "find and verify what is actually true about this topic."** The tool gives a verdict on the claim and shows the passages in your library that support or contradict it. If nothing you have read covers it, it says so and labels the verdict as the model's own, unverified.

**Ask 2, "this source says it is already verified; do I trust that?"** A source's own claim to be checked earns nothing. The tool checks the claim against your library the same way as ask 1 and says what is independently supported and what is not.

**Ask 3, "here is my explanation in my own words; where is it wrong or hand-wavy?"** The tool pulls the source passages and grades your explanation against them as wrong, fluent but wrong, partial, correct or complete. It says what is missing and logs a mistake when you are wrong. This is the deep ask and gets the most time.

**Ask 4, "did I understand that, or just recognise the vocabulary? Is this from a report I have read?"** The questioner quizzes you with questions that avoid the source's own wording, so recognising a term is not enough. It also names which stored source the idea came from, or says it is not in your library.

**Ask 5, "what should I re-check before I trust myself to use this at work?"** The tool reads your mistake log and your untested cards on the topic and returns a short re-check list. The final call stays with you, as your charter says.

**The questioner** is the name for the part that writes the questions and cards. It serves asks 4 and 5 and step 3 of the learning loop.

**Steelman** is a stretch, not a sixth ask. After ask 3 grades you, it adds the strongest case against your explanation. It is built on Friday only if everything else is passing.

## The learning loop

This is the part that makes it a learning system. Everything else exists to serve these six steps.

1. **Source in.** You paste text, upload a file or send a link.
2. **Index.** The source is split into passages and stored so they can be searched by meaning.
3. **Cards and questions.** The system writes flashcards and open questions from the source, each linked to the passage it came from.
4. **You explain.** You answer a card or explain the idea in your own words.
5. **Grade against the source.** Your answer is graded against the stored passage, not against how confident it sounds. Wrong answers go into a mistake log.
6. **Re-check.** The mistake log and untested cards drive what you are asked next and what ask 5 tells you to re-check.

Flashcard generation was cut in version 1. It is back in, because without it there is nothing to learn from.

## What goes in

Three source types are in for Sunday: pasted text or a markdown file, a PDF, and an article link. The markdown route covers your Reader and Obsidian highlights as an exported file, with no live sync.

YouTube by subtitles only is the second stretch goal for Friday, after steelman, built only if everything else is passing.

Every source is stored as passages in a vector database, which is a store that finds text by meaning and not by exact words. Asks 1 to 4 all need it to answer "what did I read about this".

This is where I narrowed your list, for two reasons. Your own slide 2 says this is "a learning-verification agent, not a pipeline". And every extra source type is another door for poisoned content, which is the reason you gave for cutting the calendar.

The folder `ingestion/` already holds PDF, Obsidian and vector code from earlier work. I have not run it yet, so whether it is reused or replaced by a library is open until I test it.

## The spine

The trunk is five small files. `core/llm.py` is the only door to a model, using the any-llm library with a key. `core/store.py` is one SQLite file for sources, passages, cards, answers and mistakes, plus the vector index. Every row keeps its date and where it came from, because this file is the start of your lifelong record. `core/registry.py` is the list of tools the loop may call. `core/loop.py` is the hand-written agent loop from your Assignment 4 and 6 code, with the PDMA and ReAct loops as you asked. `core/web.py` serves `/health` and a token-guarded `/ask` page.

Libraries are used everywhere except the loop, which stays hand-written because the course requires it. Each library sits behind one thin adapter file.

Each ask and the ingestion step is a leaf: a tool in the registry. Deleting any leaf leaves the spine working, and `tests/test_structure.py` already enforces that.

Security is kept narrow, as you said. Keys live only in `.env` on the server and are never printed or logged. The page needs a token, so only you and the tester can use it. The model key gets a spend cap. Text inside an ingested source is always treated as content and never as an instruction.

## What passing needs

The course rules for your route ask for four things: your own loop with no agent framework, a clear deliverable someone can check, four weeks of real work, and a deployment on EC2 or Hetzner at a URL they can open. Screen design is not marked.

The MVP is judged on three checks. You marked these as the bible, so they are unchanged except that the asks and hostile inputs now match your pitch.

1. Each of the five asks, typed at the public URL, reaches the right tool and gives a correct answer.
2. Each of the three hostile inputs from slide 5 is handled: a source that claims its own authority, a fluent explanation that is confidently wrong, and an uploaded source carrying wrong information or hidden instructions.
3. When no tool covers a question, it says so and does not guess.

The course brief sets the same bar for your route as for the others: an agent with a charter, playbooks and a great many hand-written tests. So the repo also holds four things beside the code.

- `SKILL.md`, the charter: what the agent owns, what it hands to you and what it never does. Slide 4 of your pitch is the first draft.
- `playbooks/`, two to five procedures that load only when needed: grading an explanation, checking a claim, writing cards from a source.
- `tests/`, built from your own test sentences. The score is ten points per hand-written test.
- `DESIGN.md`, one page: what you taught it, what it still gets wrong and what you would want next.

## What is cut until after Sunday

Audio, video and on-screen reading of video, live Reader or Obsidian sync, the knowledge graph (a store of facts linked to each other, to be built with Graphiti), WhatsApp and Telegram, spaced-repetition scheduling, the prediction tracker, the calendar and task ranker, the morning push, Langfuse traces, database backup, the source watcher, the follow-up agent and research delegated to Claude Code or Codex.

The reason is the same for each: the three checks can be shown without it. Each one is a new leaf or a new surface later, so cutting it now removes no foundation.

**After Sunday.** The AI OS review sets the order: two weeks of real use, then the source watcher, then the follow-up agent, then the graph with Graphiti. Each is a new leaf on this same record, so nothing built this week is thrown away.

## The days

Claude writes the capstone parts from today, as you asked. You review on Tuesday and connect from Wednesday.

**Sat 14 and Sun 15: the spine and ingestion.** The five trunk files run on this machine with one fake tool called end to end. Text, markdown, PDF and link sources are stored and searchable. The charter file is written from slide 4 of your pitch.

**Mon 16: the learning loop.** Cards and questions are generated from a real source of yours. Asks 3 and 4 grade your answers and log mistakes. The grading and card-writing playbooks are written alongside.

**Tue 17: asks 1, 2 and 5.** You review the assignments and the capstone parts, and write your test sentences.

**Wed 18: deployed.** `/health` and `/ask` answer at the public Hetzner URL.

**Thu 19: your tests.** Your sentences become tests, including the three hostile inputs. Failures get fixed.

**Fri 20: routing.** All five asks route correctly, and "no tool covers this" works. Then steelman, then YouTube subtitles, only if everything is passing.

**Sat 21: dry runs** on your real sources at the public URL, the README and a one-page `DESIGN.md`.

**Sun 22: no new features.** A recorded fallback demo, then tag and submit before evening.

The risk in this schedule is the assignments. They are also due Tuesday, and they share the same four days.

## Cut order if a day slips

First, the stretches are dropped: YouTube, then steelman. Second, the article link is dropped and sources are text, markdown and PDF only. Third, ask 2 becomes a rule inside ask 1 and not its own tool. Fourth, ask 5 returns the raw mistake log without a ranked list.

Never cut: the deployment, the learning loop, ask 3, the router and the three hostile inputs.

## What I need from you

- Two or three real sources you have read recently, by Sunday: one PDF report and one article at least.
- Five real ask-3 examples by Monday: the idea, your explanation, and the verdict you expect.
- Thirty to forty test sentences in your own hand by Tuesday, fifteen at the very least, one line each, in the form "given this, it should say that". Include the three hostile inputs.
- A Hetzner server and its address by Wednesday morning.
- An answer from the instructor on what gets submitted: a repo, a video, or only the live URL.

## Settled by your comments

- The web page is the only surface for now.
- The gateway is the any-llm library with a key; no half-day test is needed.
- Libraries everywhere, with the agent loop hand-written.
- It runs on Hetzner.
- The calendar ask is removed.
- Claude writes the capstone parts now; there is no slippage allowance.
- You state what needs doing and what done means; Claude takes it forward.
- The gateway is dropped for good, and the knowledge graph waits for Graphiti after the capstone.

## Still open

**Who writes the tests.** Your comment says Claude takes it forward from your definition of done. The course brief says a test written by Claude or Codex scores zero. The one-line test sentences above are my proposed middle: you write what correct looks like, Claude writes the code that checks it. Say if you want to take the risk and have Claude write them all.

**The ingestion list.** I cut audio, video and live sync until after Sunday. The knowledge graph is settled: Graphiti, after the capstone. Confirm the rest of the cut or move items back in, knowing each one costs roughly a day.

**New libraries.** A vector database and a PDF reader are needed. I will test the existing `ingestion/` code first, then bring you one list of libraries to approve before adding any.

**What gets submitted.** Unconfirmed with the instructor.
