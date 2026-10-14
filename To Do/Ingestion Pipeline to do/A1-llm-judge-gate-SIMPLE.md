# A1 — The AI Judge, in plain English

> **Status 2026-10-13: comes after the breakup (plan 01).**
>
> Your comments on this doc are answered in the table "Your comments
> (round 2) and where each one went", just below. The decisions are
> recorded in `00-DECISIONS.md`.

This is the simple version of `A1-llm-judge-gate.md`. The full doc and your
comments are unchanged. This file explains the idea, answers your comments,
and lists what you still need to decide.

---

## Your comments (round 2) and where each one went

| Your comment | What happened |
| --- | --- |
| The 5% isn't a hard number; what reaches you is data to improve the judge | Decided (M7). Treated as a number you watch. Spot checks stay, because they're the only way to catch confident wrong yeses. |
| "So `review_policy.py` is wrong?" + one-page doc on how it works now | It isn't wrong. It does mechanical checks it was designed for, and it was never meant to judge quality. One-pager = component review **CR-05** (prompt P2). |
| The extractor marking its own homework: put it in that doc too | Included in CR-05 |
| "We built checks for informal notes and typos" | You're right, they exist (Component 8), but they're switched off for Obsidian notes (F2) and have never been used (F3). Open question O3. Also covered in CR-04. |
| Page-scanner "every photo flagged" needs changing; look at it in detail | Decided (M10). It's a section in component review **CR-02**. |
| Personal remarks are useful context; entity resolution is the real question | Decided (M9): kept. Entity resolution is open question O1, with its own doc A8. |
| Opinions: "how do we get around this?" + earlier work in the gateway docs | Open question O2, with its own doc A7. **I couldn't find your earlier work. Please point me to it.** |
| More detail on why the draft judge checks the wrong thing | Doc **A1c** (prompt P3) |
| Batch API doc, merged with adding Opus 5.5 / Sonnet 5.5 and others to the gateway | Decided (M6). Doc `To Do/Gateway to do/02-models-and-batch-api.md` (prompt P4). |
| Page-scanner "batch": what's the fix? | Doc **A5** (prompt P5) |
| Prompts folder: a doc please | Doc **A6** (prompt P6) |
| Judge as its own worker: "break up the code, then rebuild properly, once" | Decided (M1, M2). The breakup is now the first plan (`01-…`), as a move, not a rewrite. See `00-CURRENT-FLOW-AND-BREAKUP.md`. |
| Part 2 features will be reassigned in the audit | Decided (M16). Part 2 is kept for reference until the component reviews reassign it. |

**N4 and N6 are now decided** (M4 and M8). N1, N2, N3 and N5 are still
waiting for your tick below.

---

## The idea in 30 seconds

1. You highlight something (in Obsidian, or a photo of a book page).
2. An AI (the **extractor**) reads the highlight and pulls out "facts":
  - **concepts**, like "Momentum Factor"
  - **claims**, like "IT and consumer staples is a good trade"
  - **links** between concepts
3. Some rules then decide one of two things:
  - **"all clear"**: the facts go straight into your knowledge graph.
  - **"needs a human"**: the facts wait for you to click approve or reject.
4. **The plan:** add a second AI (the **judge**) that looks at the waiting
  facts and says yes or no.
  - Confident yes: approved for you.
  - Anything else: still comes to you, with the judge's note attached.
  - The judge never deletes or rejects anything by itself.

Goal: you only have to look at about 5% of highlights. [THIS IS NOT A HARD NUMBER, HOW MANY EVER THAT THE JUDGE AUTO APPROVES IS FINE, THE ONES THAT STILL COME TO ME IS DATA ON HOW WE CAN IMPROVE THE JUDGE OR WHAT WE DO NEXT] 

---



## What I found when I checked your real data

You asked: *how is the "all clear" given, why do things get rejected, and
are we solving real problems?* I looked at the actual review database.

**The sample is small:** 7 highlights and about 86 facts. Treat this as
early signs, not proof.

### 1. The "all clear" has never actually happened

- All 7 highlights were sent to you. None were auto-approved.
- The "all clear" check is plain code rules with **no AI in it**
(`review_policy.py`). [SO THIS IS WRONG THEN ? I ANOTHER ONE PAGE DOCUMENT TELL ME HOW THIS WORKS RIGHT NOW, WHAT PART OF THE CODE DOES IT SIT IN, WHAT WAS IT DESIGNED TO DO, WHAT DOES THE CODE EXPECT IT TO DO, AND ITS OVERALL POSITION IN THE CODE] 
- The only AI involved is the extractor **marking its own homework**. It says how confident it is, and whether the text looked messy. [AGAIN IN A NEW DOCUMENT PLEASE AND, ALL THE ABOVE POINTS OF INFORMATION THERE AS WELL, SO I CAN QUICKLY EDIT IT AND GET IT CHANGED]



### 2. Why things get flagged: the rules are too jumpy


| Why it was flagged                                                                                                                                             | How often | Is it a useful flag?                                                                                                               |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| The extractor said "this note is informal or has typos" [IF I AM NOT WREONG WE HAD BUILT IN CHECKS FOR THIS AND AN ENTIRE SYSTEM TO AVOID THIS FROM HAPPENING] | 5 of 7    | **No.** Your meeting notes are always informal, so they will always trip this.                                                     |
| The extractor's confidence was below 0.75                                                                                                                      | 6 of 7    | **Unclear.** There are too few facts to tell, and it isn't aimed at the real rejection causes below.                               |
| It came from a page photo                                                                                                                                      | 1 of 7    | Every photo is flagged automatically. [WE ALSO NEED TO CHANGE THIS, LETS HAVE A LOOK AT THIS IN DETAIL FOLLOWING THE ABOVE FORMAT] |
| Nothing was extracted                                                                                                                                          | 1 of 7    | Fine.                                                                                                                              |


**The catch:** these jumpy flags are the *only* reason your bad facts
reached you at all. No rule actually spots a bad fact. If you simply
loosened the rules, the bad facts would sail straight into your graph. So
you can't just switch the flags off. Something smarter has to replace them,
and that's the judge. See decision **N1** below.

### 3. Why you reject facts: this is the important part

Here is what was actually rejected, grouped by cause:


| Cause                                                              | Real example                                                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **The whole note shouldn't have come in**                          | 6 facts from `Welcome.md`, the Obsidian template note                                                                                                                                                                                                                                                                                              |
| **A question was turned into a fact**                              | "Why do they use 9 month momentum?" became the concept "9 Month Momentum"                                                                                                                                                                                                                                                                          |
| **Too generic to be worth saving**                                 | "IT Sector", "Energy Sector", "Real Estate Sector", "Growth Factor"                                                                                                                                                                                                                                                                                |
| **A meaningless link**                                             | "IT Sector RELATES_TO Consumer Staples Sector"                                                                                                                                                                                                                                                                                                     |
| **Personal or gossip notes**                                       | "lavanya looks pissed that her name wasn't taken…" [YES WHILE THIS IS FINE IN THE VECTOR DB, THIS IS USEFUL CONTEXTUAL INFORMATION ON THE PERSON I THINK WE SHOULD SAVE, NOW THE MAIN QUESTION IS ENTITY RESOLUTION AND HOW WE SAVE IT]                                                                                                            |
| **Someone's opinion stated as a general truth, or unchecked info** | "Internal building will always be worse than external", "Claude changed pricing to $200" [YES BUT HOW DO WE GET AROUND THIS ?? BECAUSE A LOT OF THIS SYSTEM WILL HAVE PERSONAL OPINIONS MINE OR SOMEONE ELSES, I TRIED TO TAKE ON THIS PROJECT AND ISSUE BEFORE AS WELL IFYOU READ THE DOCS IN THE INGESTION CODE IN THE GATEWAY YOU WILL FIND IT] |


**The key point:** the judge prompt in the current draft asks *"is this fact
supported by the highlight?"* Almost every one of these rejected facts
**would pass that test**, because the quote really is in your note. So the draft judge solves a problem you don't have, which is exactly what you suspected. [YES IN A SEPERATE DOCUMENT AS WELL PLEASE, I WANT MORE DETAIL ON THIS] 

**The fix:** rewrite the judge's question around the real causes. Things
like:

- Is this a question rather than a statement?
- Is it too generic to be worth a node?
- ~~Is it personal or gossip?~~ *Superseded 2026-10-13: personal
  remarks are **kept** (M9). The question becomes "which person is this
  about?" (O1, doc A8).*
- ~~Is it one person's opinion presented as a fact?~~ *Superseded
  2026-10-13: opinions get **labelled with who holds them**, not rejected
  (O2, doc A7). The judge would check the label is right.*
- Is the link meaningful?

Two causes are better fixed **before** the judge:

- **Template notes:** skip files like `Welcome.md` at intake.
- **Questions:** the extractor could be told not to turn questions into
facts.

---



## Answers to your comments


| Your comment                                                                                                                                                                                                                                                                           | My answer                                                                                                                                                                                                                                                                                                                   |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Investigate how "all clear" is given and why things are rejected**                                                                                                                                                                                                                   | Done, see above. The rules are all code with no AI, they flag almost everything, and the real rejection causes are different from what the draft judge checks.                                                                                                                                                              |
| **"This isn't batching. Batching means the Batch API to cut costs." [GIVE ME A DOC FOR THIS, I WILL ADD IT TO THE GATEWAY, MERGE IT WITH THE REQUIREMENT TO ADD MORE MODELS TO THE GATEWAY OPIUS 5.5 SONNET 5.5, AMONG OTHERS SINCE WE ARE ADDING THEM WE WILL DO THEM ALL TOGETHER]** | **You're right.** What the code calls "batching" just puts 4 highlights in one prompt. That is not Anthropic's Batch API.                                                                                                                                                                                                   |
| **Use the Batch API; run the judge as its own separate system, controlled from the UI**                                                                                                                                                                                                | **Agreed, and it's a better design.** The draft said the judge would *not* use the Batch API, and that should be reversed. Details below.                                                                                                                                                                                   |
| **Page-scanner "batch" feels like batch for the sake of batch [WHAT IS THE SOLUTION TO THIS, AGAIN LETS INSPECT THIS PLS IN A SIMPLE PLAN SO WE ARE HAPPY WITH IT]**                                                                                                                   | Agreed. There it's just a name for a group of photos.                                                                                                                                                                                                                                                                       |
| **"A failed call gets retried next run" is interesting**                                                                                                                                                                                                                               | With the Batch API this becomes simple. Any fact that fails or times out stays in your queue and is sent again in the next batch. Nothing is lost.                                                                                                                                                                          |
| **Need to add Opus 5.5 to the gateway**                                                                                                                                                                                                                                                | Confirmed. Right now the gateway only knows Sonnet 4.6 and Haiku 4.5. It needs a model entry (`profiles.yaml`) **and** a price entry (`pricing.yaml`, which only has the older `claude-opus-5`). [AS MENTIONED ABOVE WE WILL DO THIS ALL TOGETHER]                                                                          |
| **Put prompts in** `gateway/src/`**, in an "ingestion prompts" folder with a "judge prompt" file**                                                                                                                                                                                     | Yes. One small tweak: I'd put it one level in, at `gateway/src/gateway/ingestion_prompts/judge_prompt.md`. That keeps it with the rest of the gateway code. Wherever it goes, it needs one setting so `.md` files get included when the gateway is installed. Right now nothing includes them. [YES A DOCUMENT ON THIS PLS] |
| **The policy should be its own file and looked at separately**                                                                                                                                                                                                                         | Agreed. The policy decides when a judge "yes" counts as approval. It deserves its own doc. I can move it to `A1b-judge-policy.md` and leave a pointer behind.                                                                                                                                                               |


---



## How the Batch API version would work

**What the Batch API is:** you send Anthropic a big pile of requests at
once. They send back all the answers later, usually within minutes and at
most 24 hours. In exchange, it costs **half price**.

**Why it fits the judge so well:** the facts the judge checks are already
waiting in your queue. Nothing is blocked while it thinks, so waiting is
free.

**The judge becomes its own little worker: [THIS IS WHAT I WANT TO BUILD, BUT I HAVE NOT BEEN ABLE TO, AND NOW LETS DO THIS, THE INGESTION CODE HAS BECOME VERY BLOATED WIHT MULTIPLE SMALLER INDEPDNEDNT THINGS BUNDLED TOGETHER, SINCE I AM NOT ALL THAT HAPPPY WITH ANY OF THEM, I THINK I WANT TO START WITH BREAKING UP THE CODE THEN REBUILDING IT PROPERLY AND ONLY ONCE AGAIN FOR NOW, SO I CAN ACTUALLY SAY THIS IS DONE, CLAUDE TELL ME WHAT YOU THINK]**

```text
Every so often (on its own schedule):
  1. COLLECT  - gather every waiting fact that hasn't been judged yet
  2. SEND     - submit them to Anthropic as one Batch API job (half price)
  3. CHECK    - later, ask "is the batch done yet?"
  4. APPLY    - write down each yes/no
                confident yes -> approved
                anything else -> stays in your queue with the judge's note
  5. Anything that failed or expired stays waiting and goes in the next batch.
```

**What the UI gives you:** one place to see and control it. That means
"run now", "pause", the last batch's status, cost, and how often the judge
agreed with you.

**One extra piece of work:** the gateway can't send Batch API jobs today. The
rule is that all AI calls go through the gateway, so the gateway needs a new
"send a batch / check a batch" ability first.

---



## What stays the same from the full doc

- The judge only says **yes or no**, plus a confidence score and a short
reason. It never rewrites anything.
- **It never rejects on its own.** A "no" just sends the fact to you with a note.
- A random **5% of its yeses** come to you anyway, as spot checks to catch it
being wrong.
- Risky fact types **always** come to you, such as "X is the same as Y"
merges.
- Two new database tables record every judge call and every verdict.
- The fun "postal clerk" stamp in the UI: APPROVED / RETURN TO SENDER.
- When a highlight does come to you, you can decide all its facts with one
click of submit.

---



## Every feature, and where it lives in the code

This section puts the technical detail back, explained in plain words. For
each feature you get three things:

- **What** it does.
- **Read today**: existing code worth opening first.
- **Build**: what gets created or changed.

All paths start from the `AI OS` folder. I re-checked every line number
against the code on 2026-10-12.

Some features depend on a decision at the bottom of this doc. Those are
marked *(needs N1)*, *(needs N4)* and so on.

### Part 1 — Code to read first (nothing changes here)

This is the path a highlight takes today, in order.


| Step | What happens                                                     | Where                                                                                                                                         |
| ---- | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | Obsidian notes are picked, using an include/exclude filter       | `gateway/src/gateway/ingestion/sources/obsidian.py:52` (`load_filters`)                                                                       |
| 2    | All waiting highlights are gathered, then split into groups of 4 | `pipeline.py:697` (`process_pending`), `pipeline.py:598` (`_extract_pending`), group size at `config.py:165`                                  |
| 3    | The extractor AI is called through the gateway                   | `ingestion/extraction/gateway.py:45` (`ChatClient`), extractor prompts in `ingestion/extraction/prompts.py`                                   |
| 4    | **The "all clear" rules run** (plain code, no AI)                | `ingestion/review_policy.py`, the whole file (about 200 lines). Called from `pipeline.py:456`. The 0.75 confidence line is at `config.py:157` |
| 5a   | No flags: published straight away                                | Inside `pipeline.py:448` (`_build_envelope`)                                                                                                  |
| 5b   | Any flag: queued for you                                         | `pipeline.py:569` → `store.py:545` (`queue_review`). Tables at `store.py:117` (`review_queue`) and `store.py:129` (`review_items`)            |
| 6    | The review screen shows one fact at a time                       | `ingestion/coordinator/coordinator.py:724` (`_pending_proposal`), UI in `shell/src/screens/KnowledgeProposalReview.tsx`                       |
| 7    | Your click is saved and published                                | `server.py:687` (`/run/decision`) → `coordinator.py:992` (`submit_decision`) → `pipeline.py:745` (`resolve_proposal_reviews`)                 |
| 8    | The graph silently drops facts that have no quote                | `ingestion/consumers/kg_consumer.py:109` and `:177`                                                                                           |


`pipeline.py`, `config.py`, `store.py` and `server.py` are all in
`gateway/src/gateway/ingestion/`.

**Bug spotted while checking:** the Obsidian filter file is missing. The
code looks for `gateway/src/config/obsidian_filters.txt`, but that file
didn't come across in the move to the gateway. It still sits in
`Original Code/ingestion-pipeline/merged-ingestion/config/`. When the file
is missing, `load_filters` quietly returns "no rules"
(`obsidian.py:62`). So right now **nothing is excluded**: not `.trash`,
not `Notion`, not `Readwise`. That's probably part of why `Welcome.md` got
in. I haven't changed anything. Tell me if you want it fixed.

### Part 2 — Features to build [THIS WILL HAVE TO BE REASSIGNED AS I AM DOING A FULL LEVEL AUDIT] 

**F1. Opus 5.5 in the gateway**

- **What:** let the gateway call Opus 5.5.
- **Read today:** `gateway/config/profiles.yaml`, which has only Sonnet
4.6 and Haiku 4.5. Also `gateway/config/pricing.yaml:311`, which has the
older `claude-opus-5`.
- **Build:**
  - a `knowledge-judge-v1` profile pointing at `claude-opus-5-5`
  - a price entry for `claude-opus-5-5`

**F2. Batch API in the gateway** *(needs N4)*

- **What:** the gateway learns to submit a batch of requests, ask whether
it's done, and collect the answers. It costs half price, and answers
arrive within 24 hours at most.
- **Read today:**
  - the Anthropic provider, `gateway/src/gateway/llm/providers/anthropic/__init__.py:22` (`AnthropicProvider`). Today it only has a normal `chat` call (line 64).
  - `pricing.yaml`, where `batch_multiplier: 0.5` is already written down but never used.
- **Build:** submit / check / collect batch functions in the provider, and a
way for the ingestion code to reach them through the gateway. Ground rule
R1 says no direct calls to Anthropic. I haven't designed the exact shape
of this yet, because it's the biggest new piece.

**F3. The prompt file** *(needs N5)*

- **What:** the judge's instructions live in a plain `.md` file you can
edit, not inside the code.
- **Build:**
  - `gateway/src/gateway/ingestion_prompts/judge_prompt.md`
  - a tiny loader that reads the file
  - one setting in `gateway/pyproject.toml` so `.md` files ship when the
  gateway is installed. Nothing includes them today.
  - Every judge call records a fingerprint (hash) of the prompt, so you
  can tell which prompt version produced which verdict.
- **Draft prompt**, rewritten around your real rejection causes *(needs
N2)*:

```text
You review facts that another AI pulled out of short highlighted passages
from my personal notes. For each fact, answer: should this go into my
knowledge graph as it is?

Say NO if any of these are true:
- It isn't actually in the HIGHLIGHT. Context only helps work out
  words like "he" or "it".
- It turns a QUESTION or a "maybe" into a statement.
- It's too generic to be worth saving on its own (e.g. "Energy Sector").
- It's a link that says nothing (e.g. "A RELATES_TO B").
- [SUPERSEDED by M9: personal remarks are kept, so remove this line]
  It's personal remarks or gossip about a person.
- [SUPERSEDED by O2: opinions are labelled, not rejected. Rewrite as
  "the person holding this opinion is wrong or missing".]
  It states one person's opinion, or an unchecked number, as a general fact.
- It flips the direction, overstates, or drops a "not".

Otherwise say YES. Never fix or rewrite anything. Just answer.

confidence = your real probability (0.0-1.0) that your answer is right.
reason = one short sentence I can read in two seconds.
Reply with JSON only:
{"verdicts": [{"proposal_id": "...", "approve": true, "confidence": 0.0,
  "reason": "..."}]}
```

**F4. The judge module**

- **What:** builds the request for each highlight and reads the answers
strictly.
  - If any fact's answer is missing, garbled or repeated, that fact
  goes to you.
- **Build:** `gateway/src/gateway/ingestion/judge.py`.
  - It contains a `ProposalJudge` interface and a real `LLMProposalJudge`.
  - It plugs into the pipeline the same way the extractor does.
  - It must not import `anthropic` or `openai` directly.

**F5. The judge worker** *(needs N4)*

- **What:** the background job that runs on its own schedule. It does
collect → send → check → apply, as described above.
- **Build:**
  - a worker that does those four steps
  - a store function to find facts not judged yet (`review_items_pending_judgement`)
  - a record of each batch job, so a restart doesn't lose track of a batch
  that's still running
- **Where it runs:** separate from `process_pending`. The original doc put
the judge *inside* `process_pending`, and that changes with the Batch API.

**F6. Database tables**

- **What:** two new tables next to the existing review tables in
`Database/sqlite/ingestion.db`.
  - Nothing existing changes.
  - "If not exists" means old databases just gain the new tables.
- **Your decision isn't copied:** it already lives in
`review_items.decision` and `review_items.resolver`, and the judge tables
link to it.

```sql
-- One row per Batch API job: what was sent and what came back.
CREATE TABLE IF NOT EXISTS judge_batches (
    id            TEXT PRIMARY KEY,
    batch_id      TEXT,               -- Anthropic's id for the job
    status        TEXT NOT NULL,      -- 'submitted' | 'ended' | 'failed'
    profile       TEXT NOT NULL,      -- 'knowledge-judge-v1'
    model         TEXT NOT NULL,      -- 'claude-opus-5-5'
    prompt_sha    TEXT NOT NULL,      -- which version of the prompt
    fact_count    INTEGER NOT NULL,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    cost_usd      REAL,
    error         TEXT,
    submitted_at  TEXT NOT NULL,
    ended_at      TEXT
);

-- One row per fact the judge looked at (or was not allowed to look at).
CREATE TABLE IF NOT EXISTS judge_verdicts (
    review_item_id TEXT PRIMARY KEY,  -- = review_items.id (one fact)
    envelope_id    TEXT NOT NULL,     -- the highlight it belongs to
    proposal_id    TEXT NOT NULL,
    batch_row_id   TEXT,              -- NULL for human_only
    raw_response   TEXT,              -- the judge's reply, word for word
    approve        INTEGER,           -- 1 yes, 0 no, NULL not asked / no answer
    confidence     REAL,
    reason         TEXT,
    action         TEXT NOT NULL,     -- 'auto_approved' | 'spot_check' | 'to_human' | 'human_only'
    created_at     TEXT NOT NULL,
    FOREIGN KEY(review_item_id) REFERENCES review_items(id),
    FOREIGN KEY(batch_row_id) REFERENCES judge_batches(id)
);
```

This replaces the original doc's `judge_calls` table with `judge_batches`,
because one row per batch fits the Batch API.

**F7. Acting on the verdicts** *(details move to the policy file if N6)*

- **What it does with each verdict:**
  - **Confident yes** (90% or more): approved using **the same function
  your own clicks use**, `resolve_proposal_reviews` (`pipeline.py:745`).
  It's marked with resolver `llm-judge:knowledge-judge-v1`, so you can
  always tell the judge's approvals from yours. No new way of writing to
  the graph is added.
  - **1 in 20 confident yeses:** sent to you anyway, as a spot check.
  - **No, or unsure:** stays in your queue, with the judge's note attached.
  - **Human-only flags (D1):** the judge is never asked about these.
  - **A highlight is only published once all of its facts are decided.**

**F8. Settings**

- **Build:** new settings in `gateway/src/gateway/ingestion/config.py`:
  - `judge_auto_approve_threshold` = 0.90
  - `judge_spot_check_rate` = 0.05
  - `judge_profile` = `knowledge-judge-v1`
  - `judge_human_only_signals` = the D1 list
  - how often the worker runs
- There's no on/off switch, as you asked.

**F9. Judge checks "all clear" highlights too** *(needs N1, option 1)*

- **What:** highlights with no flags stop publishing straight away. They
wait for the judge first.
  - Then the "informal note" and "low confidence" flags can be dropped from
  `review_policy.py`.
- **Read today:** `pipeline.py:448`, which is where "no flags = publish" happens.
- **Note:** the original doc listed "don't touch `review_policy.py` or the
all-clear path" as a non-goal. This feature reverses that.

**F10. Keep junk out earlier** *(needs N3)*

- **What:**
  - Restore the missing Obsidian filter file (see the bug above) and add
  `exclude Welcome.md`.
  - Optionally, tell the extractor not to turn questions into facts.
- **Read today:**
  - `obsidian.py:52`
  - the old filter file in `Original Code/ingestion-pipeline/merged-ingestion/config/obsidian_filters.txt`
  - `ingestion/extraction/prompts.py`

**F11. UI: the postal clerk**

- **What:** a stamp beside each fact on the review screen: **APPROVED**
(green) or **RETURN TO SENDER** (red), with the confidence and a
handwritten-style reason.
- **Build:**
  - a `judge` block (approve, confidence, reason, spot_check) added to
  what `coordinator.py:724` sends the UI
  - the clerk drawing in `shell/src/components/`
  - the panel in `shell/src/screens/KnowledgeProposalReview.tsx`



**F12. UI: the Judge's desk**

- **What:** one screen that shows and controls the judge:
  - a feed of every stamp, filterable by stamp, fact type, source and date
  - an agreement table showing how often the judge matched you, by fact
  type and by source
  - a "how often you had to step in" meter
  - controls *(needs N4)*: run now, pause, last batch status, cost
- **Build:**
  - `shell/src/screens/JudgeDesk.tsx` and a nav entry
  - a `GET /api/ingestion/judge/verdicts` route, plus control routes, in `server.py`
  - regenerate `openapi.json` and `shell/src/api/schema.d.ts`

**F13. Decide a whole highlight with one submit**

- **What:** when a highlight comes to you, all its waiting facts are on one
screen.
  - The doubtful fact comes first.
  - The judge's confident yeses are pre-ticked, and you can untick them.
  - Merges are never pre-ticked.
  - One submit saves them all.
- **Read today:**
  - `coordinator.py:787`, the comment saying each fact needs its own click
  - `coordinator.py:824` (`sibling_proposals`, currently read-only)
  - `coordinator.py:992` (`submit_decision`)
- **Build:**
  - an optional `decisions` list in `submit_decision` and in `server.py`'s
  request body
  - the old one-fact-at-a-time call keeps working
  - storage already supports lists (`pipeline.py:745`)

**F14. Tests (how we know it works)**

- All existing tests in `gateway/ingestion_tests/` pass with a fake judge
that says "no" to everything. That reproduces today's behaviour.
- New tests in `gateway/ingestion_tests/test_judge.py`:
  - a garbled answer goes to you
  - a "no" stays waiting
  - a human-only fact is never sent to the judge
  - a confident yes is marked `llm-judge:` and actually gets published
  - a failed or expired batch leaves its facts waiting, and they're picked
  up next time
  - the old backlog gets judged
  - every judged fact has exactly one verdict row
  - the prompt comes from the `.md` file
- New tests in `gateway/ingestion_tests/test_coordinator.py`:
  - a highlight with 3 facts is settled by one submit
  - a submit that's missing a fact, repeats one or names an unknown one is
  refused, and nothing is saved
  - the old single-fact call still works
- Checks:
  - `judge.py` has no direct `anthropic` or `openai` imports
  - the Judge's desk "auto-approved" count matches the database count

**Later, as a separate job:** move the other prompts that are currently
inside code into the prompts folder:

- `extraction/prompts.py` (3 prompts)
- `parsing.py`
- `text_cleanup/spelling.py`
- `sources/page_scanner/cleanup.py`
- `sources/book_metadata.py`

---



## Decisions for you

**New, from this pass:**

- **N1. Where does the judge sit?**
  - [ ] **Judge checks everything** (recommended). Every highlight goes past
    the judge, including ones the rules call "all clear". Then the jumpy
    "informal note" and "low confidence" flags can be dropped, and the
    judge becomes the real screen. This answers your question about putting
    a judge at the "all clear" point.
  - [ ] **Judge only clears the waiting queue** (the current draft). Keep
    the jumpy rules exactly as they are. Don't loosen them, or bad facts
    get through unchecked.
- **N2. Rewrite the judge's question around the real rejection causes**
(questions, generic, meaningless links; **not** gossip or opinion any
more, per M9 and O2)?
  - [ ] Yes (recommended)
- **N3. Skip template notes like** `Welcome.md` **at intake?**
  - [ ] Yes
- **N4. Switch the judge to the Batch API, as its own worker controlled from
the UI?** This replaces old decision D7 about batch size.
  - [x] **Decided 2026-10-13 (M4)**
  - Note: with the Batch API, each highlight can be its own request inside
  the batch. If one fails, the others are fine.
- **N5. Prompt location:** `gateway/src/gateway/ingestion_prompts/judge_prompt.md`?
  - [ ] Yes
- **N6. Move the policy into its own file,** `A1b-judge-policy.md`**?**
  - [x] **Decided 2026-10-13 (M8)**

**Still open from the full doc, in short:**

- **D1:** which flags always go to a human. The recommendation: merges,
missing quotes, wrong-document quotes, empty results and pending typo fixes.
- **D2:** the judge never auto-rejects. Confirm.
- **D3:** go live on day one, with no trial period. Confirm.
- **D4:** keep the API version at v1, since nothing breaks.
- **D6:** start at 90% confidence to auto-approve, with 5% spot checks.
- **D8:** keep the judge's one-line reason (recommended).

