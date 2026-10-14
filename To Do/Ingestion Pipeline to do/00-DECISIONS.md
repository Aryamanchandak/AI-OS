# Ingestion: Decisions Log

The one place that records **what has been decided**, **what is still
waiting for you**, and **what we found in the code**. Other plans point
here instead of repeating it.

Last updated: 2026-10-13.

---

## 1. Decided (by you)

| # | Decision | Date | Where it came from |
| --- | --- | --- | --- |
| M1 | **Break up the code first, before building anything new.** The breakup is now the first plan, ahead of the judge, intake gates, MCP and batching. This reverses the old "build features first, restructure later" order. | 2026-10-13 | Your comment in `A1-llm-judge-gate-SIMPLE.md`; this chat |
| M2 | **Breaking up, not rewriting.** Code is moved into clear, separate pieces. Its behaviour does not change. Every piece is proven to still work with **targeted checks**. Bugs found along the way are written down and fixed separately, never inside a move. | 2026-10-13 | This chat |
| M3 | **A review plan for every major component**, written before that component is moved. | 2026-10-13 | This chat |
| M4 | **The judge uses Anthropic's Batch API** (half price, answers within 24h). It runs as **its own separate worker** on its own schedule. It's controlled from one place in the UI. It still **shares the review queue**: it reads the waiting facts and approves through the same function your clicks use. | 2026-10-13 | Comment on the batching table in `A1-llm-judge-gate.md` |
| M5 | **What the code calls "batching" today isn't real batching.** It packs 4 highlights into one prompt, which is not the Batch API. The page-scanner "batch" is just a name for a group of photos. | 2026-10-13 | Comments in `A1-llm-judge-gate.md` |
| M6 | **New models and the Batch API go into the gateway together, as one piece of work.** That means Opus 5.5 and Sonnet 5.5 "among others", plus Batch API support. (Haiku 5.5 and the "others" are recommended, not yet decided. The gateway doc will ask.) | 2026-10-13 | Comment in `A1-llm-judge-gate-SIMPLE.md` |
| M7 | **The 5% "human touch" figure is not a target.** It's a number you watch. Whatever the judge auto-approves is fine. What still reaches you is data for improving the judge. | 2026-10-13 | Comment in `A1-llm-judge-gate-SIMPLE.md` |
| M8 | **The judge's policy gets its own document**, looked at on its own. | 2026-10-13 | Comment in `A1-llm-judge-gate.md` |
| M9 | **Personal remarks about people are kept**, not rejected. They're useful context about that person. The open question is *entity resolution* (which "Lavanya"?) and how it's stored. | 2026-10-13 | Comment in `A1-llm-judge-gate-SIMPLE.md` |
| M10 | **The page-scanner "always flag every photo" rule will change.** It gets its own one-page review first. | 2026-10-13 | Comment in `A1-llm-judge-gate-SIMPLE.md` |
| M11 | **The judge says yes or no only.** It also gives a confidence and a one-line reason. It never rewrites, converts or quotes. | 2026-09-28 | Earlier round (R1 in `A1-llm-judge-gate.md`) |
| M12 | **No kill switch, no shadow or watch-only mode.** If the judge fails, its facts simply stay in your queue. | 2026-09-28 | Earlier round |
| M13 | **Prompts live in files, not in code.** The judge's prompt goes in an ingestion prompts folder under `gateway/src/`. | 2026-09-28 / 2026-10-13 | Comments in both A1 docs |
| M14 | **The old "approve a whole sentence" plan (A2) is folded into A1.** What survives: when a highlight reaches you, all its waiting facts are decided in one submit. | 2026-09-28 | Earlier round |
| M15 | **The ledger is moved, never rewritten.** It's the crash-recovery record of each step. | 2026-09-27 | Roadmap rule, still holds |
| M16 | **The feature list in A1 (Part 2) is reassigned after the breakup and audit.** | 2026-10-13 | Comment in `A1-llm-judge-gate-SIMPLE.md` |

---

## 2. Recommended, waiting for your tick

Nothing here is decided. The boxes are in the documents named.

**From `A1-llm-judge-gate-SIMPLE.md`:**

| # | Question | My recommendation |
| --- | --- | --- |
| N1 | Where does the judge sit? | It checks **every** highlight, including "all clear" ones, and replaces the noisy flags. |
| N2 | Rewrite the judge's question around the real reasons you reject facts? | Yes. This now has to account for M9 and opinions (see O2), so "gossip" and "opinion" are no longer reasons to say no. |
| N3 | Skip template notes like `Welcome.md` at intake? | Yes |
| N4 | Batch API judge worker | **Decided** as M4. N4 is closed. |
| N5 | Prompt location | `gateway/src/gateway/ingestion_prompts/judge_prompt.md` (see document W6 below) |
| N6 | Policy in its own file | **Decided** as M8. N6 is closed. |

**From `A1-llm-judge-gate.md` (older, still open):**

| # | Question | My recommendation |
| --- | --- | --- |
| D1 | Which flags always go to a human? | Merges, missing quotes, wrong-document quotes, empty results, pending typo fixes |
| D2 | The judge never auto-rejects | Confirm |
| D3 | Go live on day one, no trial | Confirm (matches M12) |
| D4 | API version | Stay on v1 |
| D6 | Starting numbers | 90% confidence to auto-approve, 5% spot checks |
| D7 | Batch size | **Replaced** by M4. It gets reworded in the gateway Batch API doc. |
| D8 | Keep the one-line reason? | Keep |

**From `02-pipeline-staging-and-batching.md`:** Decisions 1–4 (what closes a
batch, slow items, lanes, vector store timing). These are still open, and
they come after the breakup.

**From `A4-intake-gates-review.md`:** Decisions 1–6. Still open.

---

## 3. Open questions (need a discussion, not a tick)

| # | Question | Notes |
| --- | --- | --- |
| O1 | **Entity resolution for people** | Personal remarks are kept (M9). How do we know which person is meant, and where does the remark get stored? Is it a vector only, a note on the person in the graph, or both? |
| O2 | **Opinions** | Much of your material is opinions, yours or other people's. My suggestion: don't reject them, **label who holds them and when** ("Bernstein analyst says X, 2026-04"). The graph already tracks claim status (current / superseded / disputed / retracted) and claim links (SUPERSEDES / CONTRADICTS / SUPPORTS). But nothing records *who* holds a claim, and the pipeline never creates claim links. **You mentioned earlier work on this. Please point me to it.** I couldn't find it in the gateway's ingestion docs. |
| O3 | **The typo-cleanup system for Obsidian notes** | It exists, but it's switched off for Obsidian (finding F2). Should it run on Obsidian highlights? |

---

## 4. Findings from the code (facts, not decisions)

| # | Finding | Where | Status |
| --- | --- | --- | --- |
| F1 | **The Obsidian filter file is missing.** The code looks for `gateway/src/config/obsidian_filters.txt`, which didn't come across in the move to the gateway. When the file is missing, no rules apply, so `.trash`, `Notion` and `Readwise` would all be ingested. That's probably part of why `Welcome.md` got in. The old copy is in `Original Code/ingestion-pipeline/merged-ingestion/config/`. | `sources/obsidian.py:24`, `:62` | Not fixed (a code change, so it waits for your OK) |
| F2 | **Typo cleanup never runs on Obsidian highlights.** The pipeline uses a placeholder, `NoHighlightCleanup`, that always says "no typos", and nothing replaces it. | `pipeline.py:63` | Recorded |
| F3 | **The cleanup database is empty**: 0 remembered corrections and 0 log entries. | `Database/sqlite/text_cleanup.db` | Recorded |
| F4 | **The "all clear" has never been given on real data.** All 7 real highlights went to the human queue. | `Database/sqlite/ingestion.db` | Recorded |
| F5 | **The flags don't catch the real problems.** The rules (`review_policy.py`, plain code with no AI) fire on "informal note" and "low confidence". Your actual rejections came from template notes, questions turned into facts, too-generic labels, empty links, personal remarks and opinions. | `review_policy.py` | Recorded |
| F6 | **Claim links are never created.** `link_claims` exists in the graph code, but nothing in the pipeline calls it. | `kg/kg_store.py:704` | Recorded |
| F7 | **The Batch API isn't used anywhere.** Its 50% discount is written in `pricing.yaml` but never applied. | `gateway/config/pricing.yaml` | Recorded |
| F8 | **The gateway only knows Sonnet 4.6 and Haiku 4.5.** `pricing.yaml` has the older `claude-opus-5`, but not 5.5. | `gateway/config/profiles.yaml` | Recorded |
| F9 | **`review_policy.py` has no test of its own.** It's only exercised indirectly through the pipeline tests. | `gateway/ingestion_tests/` | Recorded, to be handled in the breakup |

---

## 5. Documents you asked for

Each one is written in a fresh chat, using the prompts in
`FRESH-CHAT-PROMPTS.md`, unless marked "this chat".

| # | Document | Path | Made by | Status |
| --- | --- | --- | --- | --- |
| W-A | Decisions log (this file) | `Ingestion Pipeline to do/00-DECISIONS.md` | This chat | Done |
| W-B | Current flow and recommended breakup | `Ingestion Pipeline to do/00-CURRENT-FLOW-AND-BREAKUP.md` | This chat | Done |
| W-C | Breakup plan, now the first plan | `Ingestion Pipeline to do/01-reader-writer-boundary-refactor.md` (rewritten) | This chat | Done |
| W1 | How the "all clear" rules work today: where they sit, what they were designed for, what the code expects of them | `Ingestion Pipeline to do/component-reviews/CR-05-review-policy.md`. This **is** the review-policy component review. | Prompt P2 (component CR-05) | To do |
| W2 | Page-scanner photo flagging, same format | Part of `component-reviews/CR-02-page-scanner.md`, as its own section | Prompt P2 (component CR-02) | To do |
| W3 | Why the draft judge checks the wrong thing, in detail | `Ingestion Pipeline to do/A1c-judge-real-rejection-causes.md` | Prompt P3 | To do |
| W4 | Gateway: new models (Opus / Sonnet / Haiku 5.5 and others) + Batch API | `Gateway to do/02-models-and-batch-api.md` | Prompt P4 | To do |
| W5 | Page-scanner "batch": a simple plan for what it should be | `Ingestion Pipeline to do/A5-page-scanner-batching.md` | Prompt P5 | To do |
| W6 | Prompts folder: location, loader, packaging | `Ingestion Pipeline to do/A6-prompts-folder.md` | Prompt P6 | To do |
| W7 | Judge policy, on its own (M8) | `Ingestion Pipeline to do/A1b-judge-policy.md` | Prompt P7 | To do |
| W8 | Opinions: who holds them, and how they're stored (O2) | `Ingestion Pipeline to do/A7-opinions-and-attribution.md` | Prompt P8 | To do, after you point me to your earlier work |
| W9 | People and entity resolution (O1) | `Ingestion Pipeline to do/A8-people-and-entity-resolution.md` | Prompt P8 | To do |
| W10 | One review per major component (M3) | `Ingestion Pipeline to do/component-reviews/CR-01 … CR-11` | Prompt P2, once per component | To do |

## Aryaman's comments

