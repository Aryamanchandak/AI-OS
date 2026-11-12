# Macro View: Ingestion, in Plain English

This is the one-page picture of the ingestion work: what the system does
today, what we want to change, and in what order. The other documents in
this folder each cover one piece. Read this one first.

The code lives in `gateway/src/gateway/ingestion/`. The old
`ingestion-pipeline/merged-ingestion/` copy is kept only as a backup.

> **Update 2026-10-13: the order has changed.** Breaking up the code now
> comes **first**, before the judge or anything else. It's a move, not a
> rewrite. See `00-DECISIONS.md` (every decision so far) and
> `00-CURRENT-FLOW-AND-BREAKUP.md` (the flow today and the recommended
> breakup). §1 and §4 below are updated, §5 is corrected, and your round-4
> comments are in §7.
>
> **Update 2026-09-28:** your second round of comments has been acted on.
> §7 lists each one and where it went. The other plans in this folder have
> been rewritten in plain English, with the file and function names moved
> to a short "Where in the code" section at the end of each.

## 1. The short version

- **What's wrong today:** reviewing is slow, and the code has become one
  tangle: several jobs are packed into each big file.
- **First (new):** review every component, then **break the code up** into
  one folder per job. Behaviour stays the same, and every move is proven
  with targeted checks.
- **Alongside:** add the new models (Opus / Sonnet / Haiku 5.5) and the
  Batch API to the gateway.
- **Then:**
  - the LLM judge, as a Batch API worker
  - intake gates
  - agents submitting content
  - holding areas and batches
  - automatic start
- **One rule holds throughout:** the crash-recovery machinery (the ledger)
  is moved, never rewritten.

## 2. What the system does today

1. **It works through dropped files one at a time.** It picks up a file,
   runs it through every check, publishes it, and only then moves to the
   next file. Once every file is done, it moves on to fact review. This
   will change after the code is broken up (plan 01, now first), when
   plan 02 adds holding areas and batches.
2. **An LLM turns each highlight into candidate facts.** A "fact" here is a
   triplet (subject, relationship, object), a claim or a concept, each tied
   to the exact words it came from.
3. **Most facts never need you.** A rule checker looks for problems: the
   quote isn't in the text, the LLM wasn't confident, it came from a photo,
   it merges two entities, and so on. If it finds nothing, the facts are
   approved and stored automatically. Only facts with a problem reach you.
   *Correction 2026-10-13:* in practice, all 7 real highlights so far
   were flagged and reached you (finding F4 in `00-DECISIONS.md`).
4. **When you review, you decide one fact at a time.** The screen shows the
   other facts from the same sentence, but you have to click through each.
   A1 fixes this for the highlights that still reach you: all of a
   highlight's facts on one screen, one submit (this was plan A2, now
   folded into A1).
5. **Several checks can stop a file before facts are ever pulled out.**
   There are five: confirm a book's identity, fix abbreviations, fix
   spelling, approve the final text, and a "continue to fact review?"
   pause. **Every dropped file needs a manual approve click today, even
   when nothing was changed.** The new plan `A4-intake-gates-review.md`
   looks at each check one by one, as you asked.
6. **Facts are written to four places:** the knowledge graph, the vector
   store, the content database, and back into the Obsidian vault.
7. **The vector store is being written to; it hasn't been forgotten.**
   Once a highlight's facts are approved, the highlight text is split into
   sentence-sized chunks, turned into embeddings, and saved in the vector
   store. Two things are worth knowing, though, and your comment about
   worker order points straight at them:
   - Highlights with no problems flagged are embedded and searchable
     straight away. But for **flagged** highlights, the vector chunks
     **wait for fact review**. Until you've approved that highlight's
     facts, it isn't searchable either, even though you already approved
     the text itself earlier.
   - The embeddings are made **one chunk at a time**, one call each. That
     goes against your "never one at a time" rule.

   Your idea is to store the sentence first and then split it into two
   workers running side by side, one making facts and one making vector
   chunks. It is now Decision 4 in `02-pipeline-staging-and-batching.md`.
8. **The drop folder is hard-coded to your Desktop.** The fix, as you
   suggested: make it a setting you can change from the app, with the
   Desktop path kept as the default. This is in A4.
9. **The review screens and their API are both served by Gateway now.**
   A3 is just the checklist that confirms it.

## 3. What the whole system is, as five ideas

1. **Something new shows up:** an Obsidian note, a dropped file, a photo of
   a book page.
2. **The text is checked and approved:** book identity, cleanup, and your
   approve click.
3. **An LLM pulls facts out of each highlighted sentence.**
4. **Flagged facts go to review; unflagged ones are approved
   automatically.**
5. **Approved results are written to the graph, the vector store, the
   content database and the vault.** A ledger records every step so a
   crash resumes exactly where it stopped.

Every item in the roadmap changes either step 2, step 4, or how steps 3
and 5 are wired together. None of them changes what the stores hold.

## 4. The plans, and the order to do them in

| File | Order | In one line |
|---|---|---|
| `00-DECISIONS.md` | Read first | Every decision, open question, finding, and the list of docs to write |
| `00-CURRENT-FLOW-AND-BREAKUP.md` | Read first | The flow today, what's tangled, and the recommended breakup |
| `INGESTION_ARCHITECTURE_REFACTOR.md` | — | The roadmap: the order of everything |
| `component-reviews/CR-01 … CR-11` | 0 | One review per piece before it moves (to be written) |
| `01-reader-writer-boundary-refactor.md` | 1: **first plan** | Break up the code: move, don't rewrite; targeted checks |
| `To Do/Gateway to do/02-models-and-batch-api.md` | 2: alongside | New models + Batch API in the gateway (to be written) |
| `A1-llm-judge-gate.md` / `-SIMPLE.md` | 3 | The LLM judge, as a Batch API worker |
| `A4-intake-gates-review.md` | 4 | Look at each intake check; make the drop folder a setting |
| `03-mcp-surface.md` | 5 | Let AI agents hand content to ingestion |
| `02-pipeline-staging-and-batching.md` | 6 | Holding areas, batches, parallel fact and vector workers |
| `05-event-driven-ingestion.md` | 7: last | Start ingestion automatically when something changes |
| `A3-ui-ownership-closeout.md` | — | Checklist: Gateway serves every screen (mostly done) |
| `04-agent-facing-database-read-access.md` | Not in this roadmap | Pointer to `To Do/AI Agent to do/02-agent-database-read-access.md` |

**Order (changed 2026-10-13):** component reviews → **01 breakup** →
(gateway models + Batch API alongside) → A1 judge → A4 → 03 → 02 → 05.
A3 just gets ticked off. The full table is in the roadmap.

## 5. Each idea, and my honest take

**LLM judge (A1).** An LLM reads each flagged fact and approves it if it's
clearly fine. Anything it's unsure about goes to you.

- *Corrected 2026-10-13:* there is **no** watch-only trial and no kill
  switch (M12).
- Safety comes from three things:
  - the judge never rejects anything
  - 5% of its yeses are spot-checked by you
  - risky fact types always go to you
- It runs as its own **Batch API worker** (M4).
- Real data showed that the draft judge checked the wrong thing (findings
  F4 and F5 in `00-DECISIONS.md`), so its question gets rewritten.

*Take:* sound, once it targets the real rejection causes.

**Approve the sentence (was A2, now part of A1).** *Take, revised:* once
the judge is live, you only see the highlights it couldn't clear, and you're
there because one fact is doubtful. A one-click "approve the whole
sentence" would wave that fact through, and at ≤ 5% of highlights it's
not a big time-saver. What's kept is the small useful part: all of a
highlight's pending facts on one screen, pre-ticked where the judge said
yes, with one submit. The bigger time-saver is now A4, because every
dropped file needs a click today.

**Look at every gate (A4).** Five checks stand between a dropped file and
fact extraction, and each has its own reason to exist. *Take:* the
compulsory approve click on every file is probably the biggest remaining
source of friction outside fact review.

**Agents submit content (03).** An agent can hand ingestion a note. It
goes through exactly the same review as everything else. It is only
stored when submitted and processed with the next batch. *Take:* small,
safe, and the first real link between the agent and ingestion.

**Split readers from writers (01).** Code that reads Obsidian or the drop
folder is kept separate from code that writes to the graph or vector store,
so the main pipeline only coordinates. In practice, adding a new source
should never mean touching the graph code, and the other way round.
*Take:* a good idea. The risk is in carrying it out, since a lot of working
code moves.

**Batching and parallel workers (02).** Work waits in holding areas and
moves through in batches, not one item at a time. This is also where
"sentence first, then facts and vector chunks in parallel" belongs.
*Take:* committed; it's the riskiest change because it touches the crash
recovery machinery.

**Automatic start (05).** Saving a note or dropping a file starts
ingestion on its own. Spotting the change and processing it stay separate
jobs: an event only adds to the waiting pile. *Take:* comes last, because
it needs 02's holding areas to land in.

## 6. Stepping back

*Rewritten 2026-10-13.* The old view here was "cheap changes first,
restructure later". You reversed it (M1): the code has become too tangled
to keep building on, so it gets broken up first.

This is safe because the breakup is a **move, not a rewrite**. Every step
is proven by targeted checks. The new features (judge, batching) are then
built once, on clean ground, in the slots the breakup leaves for them.

## 7. Your comments, and where each one went

### Round 4 (2026-10-13)

| Your comment | What happened |
|---|---|
| Break the code up first, and rebuild each piece properly, once | Breakup is now plan 01 and goes first (M1). It's a move, not a rewrite (M2), with targeted checks. New docs: `00-CURRENT-FLOW-AND-BREAKUP.md` and `00-DECISIONS.md`. |
| A review plan for every major component | 11 component reviews (CR-01 to CR-11), written in fresh chats with the prompts in `FRESH-CHAT-PROMPTS.md` |
| The Batch API, with the judge as its own worker | Decided (M4) |
| New models and the Batch API in the gateway together | Decided (M6). New gateway doc to be written (prompt P4). |
| 5% isn't a hard target; personal remarks are kept; opinions | M7 and M9 decided. Opinions and entity resolution are open questions O1 and O2, each getting its own doc. |
| Several one-page docs asked for | Listed in `00-DECISIONS.md` §5, each with its prompt |

### Round 3 (2026-09-28)

| Your comment | What happened |
|---|---|
| A2: "not sure why this should be made anymore… very narrowly useful"; "it's a backup for when the judge doesn't approve" | A2 deleted as a standalone plan. Its useful part (decide a whole highlight's facts in one submit) is now a step in A1. Order is now A1 → A4 → 03 → A3. |

### Round 2 (2026-09-28)

| Your comment | What happened |
|---|---|
| One-file-at-a-time: "we need to change this when we divide the code into sections" | Agreed. It's Stage B: 01 splits the code and 02 replaces the one-by-one loop with holding areas and batches. §2 point 1 now says so. |
| Human approves the sentence highlight, and all its facts are auto-approved; "work out how and why" | Added to A2 as the recommended approach, with a plain explanation of how and why, and the one risk. |
| "We need an individual look at all of these gates, not just one" | New plan `A4-intake-gates-review.md`. It covers each of the five checks: what it does, why it exists, and options. It also records a finding: every dropped file needs a manual approve click today. |
| Drop folder: "expose it in the UI so the user can run this anywhere" | In A4: a setting stored outside the code, editable from a settings screen, with your Desktop as the default. |
| "§3 write-up doesn't make sense" | Removed. The one useful bit is now a single plain sentence under 01's first principle. |
| Sentence first, then parallel workers for facts and vector chunks; "worried the vector store is ignored" | Checked the code. The vector store **is** written. Unflagged highlights go in straight away; flagged ones wait for fact review. Embeddings are made one chunk at a time (§2 point 7). Your parallel-workers idea is now Decision 4 in 02. |
| "Plans are too technical; make them macro" | All plans rewritten: plain English first, code pointers in an appendix at the end. |

### Round 1 (2026-09-27)

| Your comment | What happened |
|---|---|
| Make plans for the judge, grouped review and UI move | A1, A2, A3 |
| "Make doc 3 more encompassing" | 03 now covers all MCP work; events moved to 05 |
| Detailed plan for doc 04, outside this folder | `To Do/AI Agent to do/02-agent-database-read-access.md` |
| "Let's start implementation now" | Agreed; order in §4 |
| Judge should handle **most** cases | A1 scope |
| Decide the auto-approve vs raise-to-human range | A1: set from watch-only data |
| Systematically wrong in one way | A1: per-category agreement, 5% spot checks, kill switch, different model |
| Postal-lady UI | A1: the clerk with APPROVED / RETURN TO SENDER stamps |
| Grouped review vs judge? | A2: human decides many at once vs LLM decides with no click |
| MCP: "agents calling ingestion is what?" | 03, top section |
| Batching: needed, later | 02: committed, later |
| Event-driven: last, not one fact at a time | 05 |

## Aryaman's comments

Use this space to correct anything above, push back on any take in §5, or
flag an idea that's missing entirely.
