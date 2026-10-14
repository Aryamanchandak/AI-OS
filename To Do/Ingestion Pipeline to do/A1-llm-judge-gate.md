# A1 — LLM Judge Gate

> **Status 2026-10-13: comes after the breakup (plan 01) and the gateway
> models + Batch API work.**
>
> Several things here are superseded. See `00-DECISIONS.md`:
>
> - The judge now uses the **Batch API** as its own worker (M4). The
>   "won't use it" line in the batching table is reversed, and D7 is
>   replaced.
> - The policy moves to its own doc (M8).
> - The 5% is a number to watch, not a target (M7).
> - The draft prompt targets the wrong problem (F5). It gets rewritten
>   from the real rejection causes (doc A1c).
>
> Your comments below are kept as written.

Stage A, item 1 of the ingestion roadmap
(`To Do/Ingestion Pipeline to do/INGESTION_ARCHITECTURE_REFACTOR.md`).
**Allowed to start now.** Code lives at `gateway/src/gateway/ingestion/`
(the Gateway-owned copy after Plans 06/07; not
`ingestion-pipeline/merged-ingestion/`).

> **Status: draft. Nothing here is approved yet.** Open questions and
> replies to your comments are in the last section, "Sign-off sheet".

## What this is, in one paragraph

The judge is a **yes/no stamp**. The extractor has already produced the
facts. The judge looks at each fact next to the highlight it came from and
says **yes** (approve) or **no**, with a confidence number. It does not
rewrite, convert, quote or produce anything else. A confident **yes** is
approved automatically. A **no**, or a low-confidence yes, goes to the human
queue, stamped so the human sees the judge's answer. The target is that a
human is involved in **at most 5% of highlights**, falling over time. Nothing is silently thrown away. The judge never rejects anything on its own authority. 

## What the code does today (verified 2026-09-28)

1. **Some facts are already auto-approved.** `pipeline.py`
  `_build_envelope()` (line 448) runs `review_policy.assess_review()`. If it
   produces **no review signals**, every fact is approved and dispatched
   straight to the graph, vector store and content DB. Only highlights
   **with** signals are queued for a human (`store.queue_review()`). The  judge's job is to clear that queue. Every signal is listed in plain  English in the sign-off sheet (D1). [ SO WHAT WE SHOULD INVESTIGATE IS, HWO IS THE ALL CLEAR CURRENTLY GIVEN, WHY IS IT GIVEN, AND WHERE CAN WE PUT AN AI JUDGE THERE AND IF IT IS EVEN REQUIRED, ALSO AUDIT HOW AI HAS BEEN IMPLEMENTED THERE, WHAT WE ALSO NEED TO LOOK AT IS, IN THE CASES THE HIGHLIGHT GETS REJECTED, WHY DOES IT GET REJECTED, WHAT ARE THE CAUSES SO THE AI JUDGE CAN SOLVE FOR THOSE ISSUES, INSTEAD OF SOLVING ISSUES THAT DONT EXIST.]
2. **Fact review is not a** `ReviewGate`**.** `ReviewGate` is the per-file
  checkpoint mechanism: book metadata, OCR fixes, content approval. Facts
   never pass through it. They wait in the `review_items` table, and the
   coordinator only displays that table. So the judge plugs into the
   **pipeline**, not the coordinator.



## Batching: what already exists, and how the judge uses it

The batching code in place today:


| Where                                                                     | What it batches                                                                                                                                                                                                                                                                                     | How                                                                                                                                                                                                        |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `runner.py:224`                                                           | The whole run                                                                                                                                                                                                                                                                                       | Capture everything first, then process. Two phases, not item by item.                                                                                                                                      |
| `pipeline.py` `process_pending()` (line 697)                              | Highlights waiting for extraction                                                                                                                                                                                                                                                                   | Pools **every** pending highlight across all documents, including ones left over from earlier runs, from `store.highlights_pending_extraction()`.                                                          |
| `pipeline.py` `_extract_pending()` (line 598)                             | Extraction LLM calls [THIS IS NOT HOW YOU DO BATCHING RIGHT, WHEN I SAY BATCHING IT IS USING AN APPI KEY TO DO BATCHING TO REDUCE COSTS, I DONT THINK THIS IS HOW YOU DO IT]                                                                                                                        | Splits that pool into chunks of `extraction_batch_size = 4` (`config.py:165`). One LLM call per chunk. If a chunk fails, only its items stay pending, and they are picked up again next run automatically. |
| `extraction/base.py:74` `extract_highlights()` + `BatchSemanticExtractor` | The batch contract                                                                                                                                                                                                                                                                                  | Each item gets a `batch_item_id` (`h0`, `h1`…), and code checks the mapping back. There is an output budget per batch (`DEFAULT_BATCH_MAX_TOKENS = 12288`, `extraction/gateway.py:41`).                    |
| `consumers/kg_consumer.py:165`, `vector_consumer.py:148`                  | Database writes                                                                                                                                                                                                                                                                                     | Edges and vectors are written in one bulk call each.                                                                                                                                                       |
| `config/pricing.yaml` `batch_multiplier: 0.5`                             | Anthropic's Batch API discount [THIS IS WHAT YOU WANT TO USE, WHICH IS WHY ITS SO IMPORTANT FOR THIS CODE TO RUN IN PARALLEL TO EVERYTHING ELSE, ITS A COMPLETELY DIFFERENT SYSTEM RUNNING ON ITS OWN TIMELINES, ALL ITS CONNCECTION TO THE MAIN CODE IN THE UI GIVES. A UNIFIED WAY TO CONTROL IT] | **Only priced, never used.** Nothing sends through Anthropic's async Batch API, which can take up to 24h to return. The judge won't use it either.                                                         |


(Page-scanner "batch" is only a name for a set of photos, not processing.) [YES THATS WHAT IT FEELS LIKE, THAT WE ARE USING THE BATCH FOR THE SAKE FO BATCH NOT ACTUALLY PUTTING ANYTHING IN A BATCH] 

**The judge copies the same pattern: pool, then chunk.** It adds one new
phase to `process_pending()`, after extraction:

```text
process_pending()
  1. parse phase         (unchanged)
  2. extraction phase    (unchanged: pool pending highlights → chunks of 4 → 1 call each)
  3. judge phase         ← NEW
       pool  = store.review_items_pending_judgement()
               # every pending review item with no judge_verdicts row yet,
               # INCLUDING the backlog queued before the judge existed
       split into chunks of judge_batch_size highlights
       one LLM call per chunk → yes/no per fact → write rows → act
```

This gets three things with no extra code:

- **The existing backlog** is judged on the first run.
- **A failed judge call** writes no verdicts, so its items are picked up again next run, the same way failed extraction batches are. Meanwhile they sit in the human queue as they do today. [THIS IS INTERESTING SOMETHING TO DEFINITELY LOOK AT MORE ] 
- **Bigger, cheaper batches than extraction.** The judge's answer per fact
is tiny (about 40 tokens), so a batch can hold far more than 4
highlights. This is decision D7.



## How the LLM is called

- New module `gateway/src/gateway/ingestion/judge.py`. It follows the
extractor's shape: a `ProposalJudge` protocol and an `LLMProposalJudge`
class, injected into `UnifiedIngestionPipeline` the same way the
extractor is.
- It calls through the gateway's `ChatClient` (`extraction/gateway.py:45`)
with the profile `knowledge-judge-v1` in `gateway/config/profiles.yaml`, set to Opus 5.5. There are no direct provider calls (ground rule R1). Temperature is 0, and the response is JSON only. [WE NEED TO ADD THE ABILITY TO CALL OPUS 5.5 TO THE AGENT GATEWAY] 
- Every fact in the chunk is tagged with its `proposal_id`. Code checks
that every id comes back exactly once. A fact with a missing or garbled
answer goes to the human.
- **Approvals reuse the function your clicks use:**
`pipeline.resolve_proposal_reviews(..., resolver="llm-judge:knowledge-judge-v1")`
(`pipeline.py:745`). That one function settles the review rows **and**
dispatches to the graph, vector store and content DB. There is no new
write path. A highlight only publishes once all its facts are decided, so
a partial yes saves clicks but never publishes early.



### The judge's prompt

The prompt lives in a file, not in code:
`gateway/src/gateway/prompts/ingestion/knowledge_judge.md`. This is a
folder of plain `.md` prompt files. It sits under `src/` only because the
gateway runs from an installed copy, and files outside `src/` don't ship
with it. A small loader, `gateway/src/gateway/prompts.py`, reads the files. Each call records the prompt file's hash, so you can tell which prompt version produced which stamp. [IN GATEWAY UNDER SRC, UNDER THAT MAKE A FOLDE RCALL INGESTION PROMPTS WHERE YOU HAVE A FILE CALLED JUDGE PROMPTS AND THATS WHERE YOU PUT IT]

Draft:

```text
SYSTEM
You review facts that another model extracted from short highlighted
passages, for a personal knowledge graph. For each fact, answer one
question: should this fact be published as it is?

Say YES if the fact is stated or clearly implied by the HIGHLIGHT, matches
what the highlight actually says (right subject and object, right direction,
not overstated, no dropped negation), and is a sensible, well-formed
concept / claim / relation. The CONTEXT only helps resolve words like "he"
or "it". A fact supported only by the context is not supported.

Say NO otherwise. Do not fix or rewrite anything. Just answer.

confidence is your real probability (0.0–1.0) that your answer is correct.
reason is one short sentence a human can read in two seconds.

Respond with raw JSON only.

USER
{one block per highlight: HIGHLIGHT, CONTEXT, source kind; then each fact
 with proposal_id, type, the fact itself, and its evidence quote}

Return:
{"verdicts": [{"proposal_id": "...", "approve": true, "confidence": 0.0,
  "reason": "..."}]}
```



### What the judge returns, per fact

```text
approve:    true | false
confidence: 0.0–1.0
reason:     one short sentence for the stamp in the UI
```



### The policy [I THINK THIS NEEDS TO BE LOOKED AT INDEPENDENTLY, ITS NOT SIMETHING TO GET CONFUSED WITH HERE AND NEEDS TO BE LOOKED AT IN DETAIL, CAN BE A NEW FILE]


| Judge says  | Condition                             | What happens                                                                             |
| ----------- | ------------------------------------- | ---------------------------------------------------------------------------------------- |
| yes         | confidence ≥ threshold (start 0.90)   | Auto-approved and published, except for a random 5% spot check, which goes to the human. |
| yes         | confidence below threshold            | Goes to the human, stamped "judge leans yes, 0.xx".                                      |
| no          | any                                   | Goes to the human, stamped "judge says no" with the reason. **Never auto-rejected.**     |
| (not asked) | the fact has a human-only signal (D1) | Goes to the human. Recorded as `human_only`.                                             |




### Catching the judge being systematically wrong

1. **Agreement by category.** Every fact the judge stamped and a human also
  decided gives a pair: the judge's answer and yours. That covers "no"
   stamps, low-confidence stamps and spot checks. The Judge's desk groups
   those pairs by fact type, source (obsidian / page_scanner / markdown) and
   signal. If one category is bad, add it to the human-only list or raise
   the threshold. No new mechanism is needed.
2. **Spot checks (5%)** of confident yeses. These measure the error rate of
  the approvals that went through without you.
3. **Human-touch meter.** The share of all highlights that needed a human.
  The target is ≤ 5%.



## SQL tables

Two new tables in the review SQLite that `store.py` owns. They sit next to
the existing `review_queue` and `review_items`, and nothing existing
changes. New tables need no migration, because `CREATE TABLE IF NOT EXISTS`
creates them on existing databases. Adding columns to `review_items` would
need migration code.

**Your decision is not duplicated.** It already lives in
`review_items.decision` (`approve` / `reject` / `edit`) and
`review_items.resolver` (you, or `llm-judge:…`). The judge tables join to
it.

```sql
-- One row per LLM call: exactly what was sent and what came back.
CREATE TABLE IF NOT EXISTS judge_calls (
    id            TEXT PRIMARY KEY,
    profile       TEXT NOT NULL,      -- 'knowledge-judge-v1'
    model         TEXT NOT NULL,      -- 'claude-opus-5-5'
    prompt_file   TEXT NOT NULL,      -- 'ingestion/knowledge_judge.md'
    prompt_sha    TEXT NOT NULL,      -- which version of the prompt
    fact_count    INTEGER NOT NULL,   -- facts sent in this call
    input_tokens  INTEGER,
    output_tokens INTEGER,
    raw_response  TEXT,               -- the model's reply, verbatim
    error         TEXT,               -- set if the call or parse failed
    created_at    TEXT NOT NULL
);

-- One row per fact in the review queue: what the judge said and what happened.
CREATE TABLE IF NOT EXISTS judge_verdicts (
    review_item_id TEXT PRIMARY KEY,  -- = review_items.id (one fact)
    envelope_id    TEXT NOT NULL,     -- the highlight it belongs to
    proposal_id    TEXT NOT NULL,
    call_id        TEXT,              -- NULL for human_only
    approve        INTEGER,           -- 1 yes, 0 no, NULL not asked / no answer
    confidence     REAL,
    reason         TEXT,
    action         TEXT NOT NULL,     -- 'auto_approved' | 'spot_check' | 'to_human' | 'human_only'
    created_at     TEXT NOT NULL,
    FOREIGN KEY(review_item_id) REFERENCES review_items(id),
    FOREIGN KEY(call_id) REFERENCES judge_calls(id)
);
CREATE INDEX IF NOT EXISTS idx_judge_verdicts_action ON judge_verdicts(action, created_at);
```

Example rows:


| review_item_id | approve | confidence | reason                            | action        | → review_items.decision / resolver     |
| -------------- | ------- | ---------- | --------------------------------- | ------------- | -------------------------------------- |
| ri_01          | 1       | 0.97       | Highlight states this directly.   | auto_approved | approve / llm-judge:knowledge-judge-v1 |
| ri_02          | 1       | 0.95       | Stated in the highlight.          | spot_check    | approve / aryaman (you agreed)         |
| ri_03          | 0       | 0.88       | Direction is flipped: B causes A. | to_human      | reject / aryaman                       |
| ri_04          | NULL    | NULL       | Signal alias_or_identity_proposal | human_only    | pending                                |


The two queries you'll use most:

```sql
-- Everything the judge approved on its own, newest first
SELECT jv.*, ri.proposal_type, ri.original_proposal_json
FROM judge_verdicts jv JOIN review_items ri ON ri.id = jv.review_item_id
WHERE jv.action = 'auto_approved' ORDER BY jv.created_at DESC;

-- Judge vs human, by fact type
SELECT ri.proposal_type, jv.approve, ri.decision, count(*)
FROM judge_verdicts jv JOIN review_items ri ON ri.id = jv.review_item_id
WHERE jv.action IN ('spot_check', 'to_human') AND ri.status != 'pending'
GROUP BY 1, 2, 3;
```

Source and signals are not copied into the judge table. They are already on
`review_items.reason_json` and the envelope, and are joined in when needed.
`stages.py`, `LEGAL_TRANSITIONS` and the ledger are not touched.

## The UI: the postal clerk

- **Review screen** (`shell/src/screens/KnowledgeProposalReview.tsx`): an
illustrated clerk panel beside each fact. It shows a rubber stamp,
**APPROVED** (green) or **RETURN TO SENDER** (red). The confidence is on
the stamp and the reason is a handwritten note. Spot checks carry a
"spot check" tag.
- **"Judge's desk" screen** (`shell/src/screens/JudgeDesk.tsx`): a feed of
everything the clerk stamped, filterable by stamp, category and date. It
shows the agreement table and the human-touch meter.
- **Backend:** `GET /api/ingestion/judge/verdicts?since=…`, plus a `judge`
block (`approve`, `confidence`, `reason`, `spot_check`) added to the
proposal payload in `_pending_proposal()`.
- The clerk is an inline SVG in `shell/src/components/` and uses the shell
theme tokens.



### Deciding a whole highlight in one submit (was plan A2)

When a highlight comes to you, it's because the judge said no, wasn't
confident, or wasn't allowed to decide a fact. Today you then click through
each fact in that highlight separately. The other facts are shown beside it,
but read-only (`sibling_proposals` in `_pending_proposal()`). Each one needs
its own `/run/decision` call. This step fixes that, and only that:

1. **Every still-pending fact in the highlight is decidable on one screen.**
2. **The fact(s) that brought you here come first**, with the clerk's stamp
  and note. The rest of the highlight's pending facts sit below them,
   pre-ticked where the judge said a confident yes. You can untick any of
   them.
3. **One submit sends every pending fact in the highlight.**
  `submit_decision()` accepts an optional `decisions` list for
   `gate == "proposal"` next to the existing single decision. The old
   single-decision shape keeps working, so this is additive and stays on
   `v1` (D4). Storage needs no change:
   `resolve_proposal_reviews(envelope_id, decisions=[...])` already takes a
   list, rejects duplicates, writes in one transaction, and publishes once
   nothing is pending.
4. **Merge facts ("X is the same as Y") are never pre-ticked.** The judge
  isn't asked about them (D1), so they always need your own tick.

Deliberately **not** a single "approve the whole sentence" button. You're
here because one fact is doubtful, and a whole-sentence approval is the one
action that would let that fact through unread. No new LLM summary, and
extraction doesn't change. If the human-touch meter later shows you're
reviewing many highlights a week, a fuller sentence-review screen can be
reconsidered then, with real numbers behind it.

## Rollout

1. Build and go live with a threshold of 0.90 and 5% spot checks.
2. After ~100 spot checks, read the agreement table and adjust the
  threshold or the human-only list. Record the change here.
3. Monthly: re-read agreement and the human-touch meter.



## Work packages

1. `prompts/` folder, the `prompts.py` loader, and
  `prompts/ingestion/knowledge_judge.md`.
2. `judge.py`: protocol, `LLMProposalJudge`, batch prompt assembly, and a
  strict JSON parser. A missing or garbled answer goes to the human.
3. `knowledge-judge-v1` profile (Opus 5.5, which you are adding).
4. `store.py`: the two tables, `review_items_pending_judgement()`,
  `record_judge_call()` and `record_verdicts()`.
5. `pipeline.py`: the judge phase in `process_pending()`. Confident yeses go
  through `resolve_proposal_reviews(resolver="llm-judge:…")`, and outcomes
   are updated to `processed`, so the run report counts them.
6. `config.py`: `judge_auto_approve_threshold` (0.90),
  `judge_spot_check_rate` (0.05), `judge_batch_size` (D7),
   `judge_profile`, `judge_human_only_signals` (D1). No on/off switch.
7. `coordinator.py` `_pending_proposal()`: the `judge` block. Add judge
  counts to the run report.
8. `server.py`: the `/judge/verdicts` route. Regenerate `openapi.json` and
  `shell/src/api/schema.d.ts`.
9. Shell: the clerk panel, `JudgeDesk`, a nav entry, the agreement table
  and the meter.
10. Whole-highlight submit (was A2): the optional `decisions` list in
  `coordinator.py` `submit_decision()` and its `server.py` body model;
    `_pending_proposal()` serves the highlight's pending facts as decidable;
    the review screen gets per-fact ticks, pre-ticked from the judge's
    confident yeses, and a single submit. Delete the "deciding a sibling
    still requires its own `/run/decision` call" comment (~line 787).

**Follow-up cleanup (separate task):** move the existing hard-coded prompts
into `prompts/`: `extraction/prompts.py` (3), `parsing.py` (segmentation),
`text_cleanup/spelling.py`, `sources/page_scanner/cleanup.py` and
`sources/book_metadata.py` (cover classification).

## Done when (checkable)

- The existing `gateway/ingestion_tests/` suite passes unchanged with a
stub judge that says "no" to everything, which reproduces today's
behaviour.
- New tests in `gateway/ingestion_tests/test_judge.py`:
  - a garbled answer goes to the human;
  - a "no" stays pending;
  - a human-only fact is never sent and gets a `human_only` row;
  - a confident "yes" gives `review_items.resolver` starting with
  `llm-judge:`, the fake dispatcher receives the envelope, and the
  outcome is `processed`;
  - a failed judge call writes no verdicts, and the items are re-judged on
  the next run;
  - the pre-existing backlog is judged;
  - N highlights within `judge_batch_size` make exactly one judge call;
  - every judged fact has exactly one `judge_verdicts` row;
  - the prompt is loaded from the `.md` file.
- New tests in `gateway/ingestion_tests/test_coordinator.py` for the
whole-highlight submit:
  - a highlight with 3 pending facts is settled by one submit, and each
  fact is stored exactly once;
  - a submit that leaves out a pending fact, repeats one, names an unknown
  one, or says "edit" with no edit is refused, and nothing is saved;
  - the old single-decision call still works.
- `git diff` on `coordinator/stages.py` and `coordinator/state.py` is
empty. `judge.py` contains no `anthropic`/`openai` imports.
- The Judge's desk auto-approved count equals
`SELECT count(*) FROM review_items WHERE resolver LIKE 'llm-judge:%'` over
the same dates.



## Non-goals

- Changing extraction, `review_policy.py` or the no-signal auto-approve
path.
- The judge editing, rewriting or quoting anything.
- Auto-reject.
- The holding-area refactor (`02-pipeline-staging-and-batching.md`).

---



## Sign-off sheet (the only section you need to read)



### Your latest comments

**R1. "It should rubber stamp: just yes or no, no converting."**
Agreed. That was a misunderstanding on my side, and it's fixed. The
previous draft made the judge copy a supporting quote out of the text,
which is exactly the conversion you don't want. That has been removed. The
judge now returns only `approve: yes/no`, a `confidence`, and a one-line
`reason` for the stamp. I also dropped the separate "unsure" answer, because
a low-confidence yes already means unsure, and both go to you anyway.

- **Open (D8):** keep the one-line `reason`? It's what the stamp's
handwritten note shows, and what you'd read to see *why* the judge said
no. It's the only text the judge writes.
  - [ ] Keep it (recommended)
  - [ ] Drop it: yes/no and confidence only

**R2. "Want to look at the SQL table structure."**
See the "SQL tables" section. It has the full `CREATE TABLE` statements,
example rows and the two queries you'd use. In short: `judge_calls` holds
one row per LLM call, with the raw response. `judge_verdicts` holds one row
per fact. Your decision is not duplicated, because it already sits in
`review_items`, and the tables join on it.

**R3. "Does the batching consider the batching code we already have?"**
It didn't before, and it does now. See the "Batching" section: there's a
table of every piece of batching code in place, and the judge copies the
existing pool-then-chunk pattern that extraction uses. That pattern also
judges the existing backlog and retries failed calls on the next run, with
no extra code.

**R4. A2 folded in here (2026-09-28).** The standalone "approve a whole
sentence at once" plan (A2) is deleted. After the judge, you only see
highlights it couldn't clear, and you're there because of one doubtful
fact. So the useful part of A2 is small: decide all of that highlight's
pending facts on one screen with one submit. That's now in "Deciding a
whole highlight in one submit" and work package 10. Nothing to decide.

### Earlier comments (answered in the previous pass, still apply)

- **No kill switch or fallback:** there is no on/off/shadow mode. If the
judge fails, its facts stay in your queue.
- **Prompts in files:** the judge's prompt is in `prompts/`. Moving the
other 7 prompts is a follow-up.
- **ReviewGate:** the judge sits in the pipeline, because facts never go
through `ReviewGate`. Nothing for you to decide.
- **Opus 5.5:** you're adding it. The profile will point at it.



### Open decisions

**D1. Which signals must always go to a human (the judge is never asked)?**


| Signal                                                | Plain English                                                                                                                 | Recommend                                               |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `source_is_page_scanner`                              | The highlight came from a photo. **Every** photo gets this.                                                                   | Judge may clear (the 5% target is impossible otherwise) |
| `proposal_model_confidence_below_threshold`           | The extractor rated its confidence in this fact below 0.75                                                                    | Judge may clear                                         |
| `overall_model_confidence_below_threshold`            | The extractor rated the whole highlight below 0.75                                                                            | Judge may clear                                         |
| `source_quality_signal`                               | The extractor flagged the text as garbled or incomplete                                                                       | Judge may clear                                         |
| extractor-raised reasons                              | Free-form "please review" flags from the extractor                                                                            | Judge may clear                                         |
| `evidence_offsets_missing` / `evidence_range_invalid` | The quote's *position* in the text is missing or wrong. Nothing downstream uses the position.                                 | Judge may clear                                         |
| `evidence_quote_mismatch`                             | The quote doesn't match the text exactly, so it may be paraphrased. The judge sees the quote next to the highlight.           | Judge may clear                                         |
| `evidence_quote_ambiguous`                            | The quote appears twice in the highlight. This is harmless.                                                                   | Judge may clear                                         |
| `missing_evidence`                                    | The fact has no quote at all. The graph **drops** facts with no quote (`kg_consumer.py:109`), so a yes would publish nothing. | **Human-only**                                          |
| `alias_or_identity_proposal`                          | "X is the same as Y". This merges graph nodes and is hard to undo.                                                            | **Human-only**                                          |
| `evidence_source_mismatch`                            | The quote is tagged to a *different document*. This is an extractor or bookkeeping bug.                                       | **Human-only**                                          |
| `empty_semantic_extraction`                           | Nothing was extracted, so there is nothing to approve                                                                         | **Human-only**                                          |
| `cleanup_suggestion_pending`                          | Typo fixes are suggested for the text but not yet accepted. The judge approves facts, not spelling.                           | **Human-only**                                          |


- [ ] Accept the recommendation
- [ ] Change: ______

**D2. Auto-reject:** never. You asked why it would ever happen, and it
won't. Confirm:

- [ ] Confirmed

**D3. No trial period; go live on day one.** You said this. Confirm:

- [ ] Confirmed

**D4. Contract version.** The backend labels every response to the UI
`component6.v1` (`server.py:43`). It's an API version number: it gets
bumped when a change would break the UI. The judge only *adds* an optional
`judge` field, which an older UI simply ignores.

- [ ] Stay on `v1` (recommended)
- [ ] Bump to `v2`

**D6. Starting numbers:** threshold **0.90** and spot checks **5%**. Spot
checks count towards your 5% human budget. Lower them to 2% once spot-check
agreement is ≥ 98%.

- [ ] Accept
- [ ] Change: ______

**D7. Judge batch size:** how many highlights go into one judge call.

- [ ] **20 highlights per call** (recommended). That is about 50–100
  facts. The answer is small (roughly 4k tokens), so one call replaces five
  extraction-sized ones.
- [ ] 4, the same as extraction. One judge call per extraction call:
  simpler to reason about, more calls.
- [ ] Other: ______

**D8. Keep the one-line reason?** See R1 above.