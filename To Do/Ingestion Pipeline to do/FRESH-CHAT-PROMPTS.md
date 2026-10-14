# Prompts for Fresh Chats

These are the documents too big to do in one chat. To use one:

1. Open a fresh Claude Code chat in the `AI OS` folder.
2. Paste **P1 (the shared header)** followed by **one** of P2–P8.
3. Each prompt writes exactly one document, except P2, which you run once
   per component.

**Suggested order:**

- P2 for CR-09 first (the writers are the first move), and CR-05 (its
  pinning tests are part of the safety net before any move).
- Then the rest of P2.
- P4 can run any time, since it's gateway work.
- P3, P5, P6, P7 and P8 come when you want them.

After each chat:

1. Tick the document off in `00-DECISIONS.md` §5.
2. Read it and add your comments.

---

## P1: Shared header (paste this first, every time)

```text
You are working in the repository at "/Users/aryamanchandak/Documents/AI OS".
This is a DOCUMENTS-ONLY task: do not change any code, config or database.
Read-only commands (grep, sqlite3 -readonly, running tests) are fine.

Before anything else, read these, in order:
1. To Do/Ingestion Pipeline to do/00-DECISIONS.md   (all decisions, findings, open questions)
2. To Do/Ingestion Pipeline to do/00-CURRENT-FLOW-AND-BREAKUP.md   (the flow today + the target breakup)
3. To Do/Ingestion Pipeline to do/01-reader-writer-boundary-refactor.md   (the breakup plan and "targeted checks")

Context: the ingestion code lives in gateway/src/gateway/ingestion/ and
its tests in gateway/ingestion_tests/. We are about to BREAK UP this code
(move it into one folder per job) WITHOUT changing behaviour. Nothing new
is built during the breakup.

Rules for the document you write:
- Plain English first. The reader finds dense technical docs hard to
  read. Short sentences, tables, no jargon without a one-line explanation.
- Put file paths, function names and line numbers in a "Where in the
  code" section at the END. Check every line number against today's code;
  don't copy old numbers.
- Base claims on the code and data you actually read. If you didn't check
  something, say so. Don't guess.
- Decisions the reader must make go in a "Decisions" section as tick
  boxes, each with a recommendation and a one-line reason.
- End with an empty "## Aryaman's comments" section.
- If a document you're asked to edit has bracketed [CAPS] comments from
  Aryaman, keep them exactly as written.
- When done, update that document's row in 00-DECISIONS.md §5 to "Done"
  and reply with a 5-line summary plus any questions.
```

---

## P2: Component review (run once per component)

Replace `<CR-ID>`, `<NAME>` and `<FILES>` with a row from the table below.

```text
Write the component review <CR-ID>: <NAME>.
Output: To Do/Ingestion Pipeline to do/component-reviews/<CR-ID>-<short-name>.md

Files in scope: <FILES>
Read every file in scope fully, plus the code that calls into it and the
tests that cover it (search gateway/ingestion_tests/ for its classes and
functions, including indirect coverage).

The review must answer, in this order:
1. What it does today, in plain words (with a small worked example if it helps).
2. Where it sits in the flow (which of the 10 steps in 00-CURRENT-FLOW-AND-BREAKUP.md §1).
3. What it was designed to do (docstrings, comments, old plan docs in
   "Original Code/ingestion-pipeline/" and "To Do/Gateway to do/").
4. What the rest of the code expects of it: who calls it, with what, and
   what they rely on getting back.
5. Does 3 match what it actually does? List every mismatch, bug or dead code found.
6. Tests today: what's covered, and the gaps.
7. Targeted checks to add BEFORE it moves: small, isolated tests that pin
   today's behaviour (describe them; don't write them).
8. Where it lands in the breakup (target folder from §4 of the breakup
   doc), what moves with it, and anything that makes the move risky.
9. Decisions for Aryaman (tick boxes).
Then "Where in the code" and "## Aryaman's comments".

Bugs you find are RECORDED, not fixed. The breakup rule is "no fixes inside a move".
```

| CR-ID | Name | Files | Extra instruction |
| --- | --- | --- | --- |
| CR-01 | Obsidian and folder readers | `sources/obsidian.py`, `sources/markdown_tree.py` | Cover finding F1 (missing filter file) and where the file should live |
| CR-02 | Page scanner and book identity | `sources/page_scanner/*`, `sources/book_metadata.py`, `intake/extractors/image.py` | **Include a separate one-page section: "Why every photo is flagged"** (decision M10). Cover why the `source_is_page_scanner` flag exists, what it protects against, and options to change it. |
| CR-03 | Drop-folder intake and file readers | `intake/*`, `intake/extractors/*` (not image.py) | Cover the hard-coded Desktop drop folder |
| CR-04 | Intake checks and text cleanup | `coordinator/gates.py`, `text_cleanup/*` | Cover findings F2 and F3 (cleanup never runs on Obsidian notes; empty cleanup DB) and open question O3 |
| CR-05 | Flag rules ("all clear") | `review_policy.py`, and its call site in `pipeline.py` (`_build_envelope`) | **This is the "how the all-clear works" one-pager Aryaman asked for. Keep sections 1–4 to about one page so he can edit it quickly.** Include "the extractor marks its own homework" (its self-reported confidence and quality signals) and the real numbers from `Database/sqlite/ingestion.db` (read-only) |
| CR-06 | Capture and splitting into highlights | `pipeline.py` `capture()`, `normalization.py`, `ids.py`, `parsing.py` | |
| CR-07 | Fact extraction | `extraction/*`, `pipeline.py` `parse_source()` / `_extract_pending()` / `process_pending()` | Cover what "batching" means here today (4 highlights per prompt; decision M5) |
| CR-08 | Ingestion database and review queue | `store.py`, `models.py`, `pipeline.py` `resolve_review()` / `resolve_proposal_reviews()` | Note that `IngestionStore` has no test of its own |
| CR-09 | Writers and dispatch | `consumers/*`, `kg/*`, `vector/*`, `content_store.py`, `publish/*`, `dispatch.py`, `routing.py` | Cover finding F6 (`link_claims` never called) and the one-embedding-call-per-chunk behaviour |
| CR-10 | Run coordinator, ledger, runner and API | `coordinator/*`, `runner.py`, `server.py`, `routes.py`, `setup.py`, `preview.py`, `config.py` | The ledger (`stages.py`, `state.py`) is moved, never rewritten. Map `view()` (about 600 lines) into its parts. |
| CR-11 | AI access | `http_client.py`, `extraction/gateway.py`, the ChatClient definitions in `parsing.py` and `runner.py`, `text_cleanup/spelling.py`, `sources/page_scanner/cleanup.py`, `sources/book_metadata.py` | List every place the AI is called, and propose the single access path. Link to the gateway doc from P4 if it exists. |

---

## P3: Why the draft judge checks the wrong thing (A1c)

```text
Write: To Do/Ingestion Pipeline to do/A1c-judge-real-rejection-causes.md

Also read: A1-llm-judge-gate.md and A1-llm-judge-gate-SIMPLE.md in the same
folder (keep their [CAPS] comments untouched; don't edit them).

Goal: show in detail why the draft judge prompt (which asks "is this fact
supported by the highlight?") would approve almost everything Aryaman
actually rejected.

Steps:
1. From Database/sqlite/ingestion.db (open read-only), list every
   rejected or edited fact (review_items.decision in reject/edit), with
   the highlight text it came from, its evidence quote, its flags
   (reason_json) and the resolution note.
2. Group them into causes (e.g. template note, question turned into a
   fact, too generic, empty link, personal remark, opinion stated as fact,
   unchecked number). Show 1-2 real examples per cause.
3. For each cause, say whether the draft judge would catch it, and why.
4. Say where each cause is best fixed: at intake (e.g. filter file), in
   the extractor's prompt, in the judge, or not at all. Respect decision
   M9 (personal remarks are KEPT) and open question O2 (opinions get
   labelled with who holds them, not rejected).
5. Propose the judge's question rewritten around the causes it should
   own (a draft prompt in a code block).
6. Be honest about the sample size (it is small: 7 highlights, about 86 facts).
```

---

## P4: Gateway: new models + Batch API (one doc, decision M6)

```text
Write: To Do/Gateway to do/02-models-and-batch-api.md

This is gateway work, not ingestion. Read the gateway docs in
"To Do/Gateway to do/" (especially the GLC migration plans 02 and 04) for
how the gateway is structured, then read:
- gateway/config/profiles.yaml and gateway/config/pricing.yaml
- gateway/src/gateway/llm/ (providers/anthropic, providers/registry.py,
  providers/capabilities.py, profiles, routing, economics, service.py)
- gateway/src/gateway/ingestion/http_client.py and extraction/gateway.py
  (how ingestion calls the gateway today)

Cover, in plain English:
Part A: Adding models.
- Which models to add: Claude Opus 5.5 (claude-opus-5-5), Sonnet 5.5
  (claude-sonnet-5-5), Haiku 5.5 (claude-haiku-5-5), "among others". Ask
  Aryaman which others in the Decisions section (e.g. other providers already
  in the registry, or newer versions of ones already configured).
- Every place a model must be registered (profiles, pricing, capabilities,
  routing...), with today's state of each (findings F7, F8 in 00-DECISIONS.md).
- The step list to add one model, so adding the next is routine.
Part B: Anthropic Message Batches API.
- What it is (submit many requests, results within 24h, 50% price).
  Check the current Anthropic docs for exact limits and behaviour rather
  than assuming.
- What the gateway needs: submit a batch, check status, fetch results,
  cancel; how results map back to requests; what happens to errored or
  expired requests (they stay pending and are resubmitted).
- How a caller (first user: the ingestion judge, decision M4) uses it
  through the gateway, never calling Anthropic directly (ground rule R1).
- Where batch jobs are tracked so a restart doesn't lose them.
- Cost tracking: the 0.5 batch_multiplier already in pricing.yaml is
  never applied today.
- How the UI controls it: status, run now, pause, cost.
Decisions as tick boxes. Don't write code.
```

---

## P5: Page-scanner "batch": what it should be (A5)

```text
Write: To Do/Ingestion Pipeline to do/A5-page-scanner-batching.md

Read: gateway/src/gateway/ingestion/sources/page_scanner/ (all files),
intake/extractors/image.py, sources/book_metadata.py, publish/vault_writer.py
(photo archiving), and how the coordinator handles photos
(coordinator/coordinator.py, coordinator/gates.py). If
component-reviews/CR-02-page-scanner.md exists, read it and don't repeat it.

Aryaman's comment: the page-scanner "batch" feels like batching for the
sake of it. It's just a name for a group of photos, and nothing is
actually processed as a batch.

Cover, simply:
1. What "batch" means in the page scanner today, step by step.
2. Where real batching would actually save time or money (e.g. OCR, the
   AI cleanup calls, the review clicks, the Batch API from decision M4/M6).
3. Two or three options, from "just rename it" to "real batching",
   each with pros and cons.
4. A recommendation, and where it fits in the order (after the breakup, M1).
```

---

## P6: Prompts folder (A6)

```text
Write: To Do/Ingestion Pipeline to do/A6-prompts-folder.md

Aryaman wants prompts in files, not code (decision M13): a folder for
ingestion prompts under gateway/src/, with a file for the judge prompt.

Read: gateway/pyproject.toml (how the package is built and which files
ship), and every place a prompt is hard-coded today: extraction/prompts.py,
parsing.py, text_cleanup/spelling.py, sources/page_scanner/cleanup.py,
sources/book_metadata.py (all under gateway/src/gateway/ingestion/).

Cover:
1. The exact folder and file names. The recommendation so far is
   gateway/src/gateway/ingestion_prompts/judge_prompt.md. Check whether a
   folder placed directly in gateway/src/ would ship, and explain the choice.
2. The packaging setting needed so .md files are included when installed
   (nothing includes them today). Verify against pyproject.toml.
3. A tiny loader: how code reads a prompt, and how each AI call records
   which prompt version (a hash) it used.
4. A list of every existing hard-coded prompt and whether/when it moves.
   Moving them happens after the breakup (M1), not during it.
5. Decisions as tick boxes.
```

---

## P7: Judge policy (A1b, decision M8)

```text
Write: To Do/Ingestion Pipeline to do/A1b-judge-policy.md

Read A1-llm-judge-gate.md ("The policy", "Catching the judge being
systematically wrong", decision D1, D6) and A1-llm-judge-gate-SIMPLE.md
(F7, N1). If A1c-judge-real-rejection-causes.md exists, read it too.
Keep all [CAPS] comments in those files untouched. The only edit allowed
there: under the "### The policy" heading in A1-llm-judge-gate.md, add one
line pointing to the new doc. Remove nothing; the heading carries
Aryaman's comment.

The policy is the set of rules that turn a judge verdict into an action.
Cover it on its own, in detail:
- What happens for each verdict: confident yes / unsure yes / no / not asked.
- The confidence threshold and spot-check rate: starting values, and how
  they get adjusted.
- Which fact types or flags are never sent to the judge (D1).
- Whether the judge checks only flagged highlights or every highlight (N1).
- The 5% is a number to watch, not a target (M7).
- No auto-reject, no kill switch (M12).
- How "the judge is wrong in one category" gets caught and acted on.
- How this works when verdicts arrive later from a Batch API job (M4).
Decisions as tick boxes.
```

---

## P8: Opinions (A7) or people and entity resolution (A8)

Run this once for A7 and once for A8. **For A7, first tell the chat where
your earlier opinions work is**, because it couldn't be found.

```text
Write ONE of:
- A7: To Do/Ingestion Pipeline to do/A7-opinions-and-attribution.md (open question O2)
- A8: To Do/Ingestion Pipeline to do/A8-people-and-entity-resolution.md (open question O1)
Which one: <A7 or A8>
<For A7 only: Aryaman's earlier work on opinions is at: ____ (read it first)>

Read: gateway/src/gateway/ingestion/kg/ (kg_store.py, models.py,
identity.py), consumers/kg_consumer.py, extraction/prompts.py,
review_policy.py (the alias_or_identity_proposal flag), and models.py.

Background: the knowledge graph is built from Aryaman's personal notes:
meetings, books and conversations. Much of it is opinion (his or other
people's) and remarks about people.
- Decision M9: personal remarks about people are KEPT. They're useful
  context about that person.
- Open question O2: opinions shouldn't be rejected; the suggestion is to
  label who holds each claim and when.
- What exists today: claims have a status (current / superseded /
  disputed / retracted) and can be linked (SUPERSEDES / CONTRADICTS /
  SUPPORTS), but nothing records who holds a claim, and the pipeline never
  calls link_claims (finding F6). Check this yourself.

For A7 (opinions): how to store "who says what, when"; how the extractor
would capture the holder; what the judge then checks; how contradicting
opinions from different people coexist.
For A8 (people): how a name in a note ("lavanya") gets matched to the
right person node; what happens when it's ambiguous; where a personal
remark is stored (vector only, a note on the person node, or both); how
it connects to the existing identity/alias machinery.
Options with pros and cons, a recommendation, decisions as tick boxes.
```

---

## Later (don't use yet): carrying out a breakup step

Use this only after a step's component review is read and agreed.

```text
(Paste P1 first, but REPLACE its first rule: this task DOES change code.)
Carry out breakup step <N> from To Do/Ingestion Pipeline to do/01-reader-writer-boundary-refactor.md.
Its component review is component-reviews/<CR-ID>-....md. Read it first.
Follow "Targeted checks" in plan 01 exactly:
1. Add or confirm the pinning tests the review lists; run them and the
   full suite; record the baseline.
2. Move the code. No behaviour changes, no fixes; keep old import paths
   working.
3. Re-run the pinning tests, the full suite, and diff openapi.json, the DB
   schema, coordinator/stages.py and state.py.
4. Record what moved and what was checked in the component review.
Commit only when everything is unchanged and green, and only if I say so.
```
