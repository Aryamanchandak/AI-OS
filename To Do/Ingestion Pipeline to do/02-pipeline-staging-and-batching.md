# 02: Holding Areas, Batches and Parallel Workers

Stage B, after plan 01. **Committed, but later.** You said: *"we need to
basically add batching... we will get there later."* It will be built;
the only question is when.

## The idea: a factory floor, not one big machine

Today a single routine takes each item all the way through, from
discovery to extraction to review to storage, one at a time.

Instead:

1. Each step becomes its own small worker.
2. Between steps there's a **holding area**: a durable waiting place,
   saved to disk.
3. A worker takes a **batch** from one holding area, does its job, and
   puts the results in the next one.

```text
new items → [waiting] → text check → [approved text] → split into sentences → [sentences]
                                                                                   ├─→ fact worker   → [facts to review] → review → [approved facts] → graph
                                                                                   └─→ vector worker → [chunks] ─────────────────────────────────→ vector store
```

**This already exists in two narrow places.** The crash-recovery ledger
already saves progress between steps, and the photo scanner already runs
as a chain of separate steps. This plan makes the whole pipeline work
that way.

**What gets better:**

- Work is done in batches, which is much cheaper for LLM and embedding
  calls.
- A crash can resume at the right *batch*, not just the right item.
- Workers can run side by side where it makes sense (Decision 4).

## What changes

- **A batch becomes the unit that moves through review**, instead of a
  single item. This is a real change to the run's step-by-step rules,
  which is why it waits until Stage B.
- **The existing per-item logic isn't thrown away.** It runs *inside* a
  batch step.
- **The ledger gains a record of which holding area each piece of work is
  in.** List those records out before starting, rather than finding them
  halfway through.

## What must not break

1. The ledger and run rules are **extended, never rewritten**.
2. After a crash, the run resumes at the right batch *and* the right item
   within it. This needs its own test.
3. A destination that already succeeded is still skipped on retry, for
   each item, even inside a batch.

## Decisions for Aryaman

### Decision 1: what closes a batch?

- **A. A count:** close after N items. Simple, but a slow trickle may
  never reach N.
- **B. A timer:** close every N hours. Regular, but sizes vary wildly.
- **C. By hand:** you press "review now". Full control, but it defeats
  automatic ingestion (plan 05).
- **D. Count or timer, whichever comes first.** A burst gets batched and a
  trickle doesn't stall.

**Recommended: D.** Automatic triggers (plan 05) also rule out "close per
event", since processing one item at a time is too expensive.

> **Aryaman's call:** _______________

### Decision 2: does one slow item hold up the whole batch?

- **A. Yes:** nothing is stored until every item in the batch is decided.
  This is simpler, but one item waiting on you blocks everything else.
- **B. No:** approved items are stored as soon as they're approved. The
  batch only groups things for review.

**Recommended: B.** It keeps today's rule that finished work is never held
back by unfinished work.

> **Aryaman's call:** _______________

### Decision 3: do clerk-approved and needs-you items share a batch?

- **A. Same batch, visibly separated.**
- **B. Separate lanes:** your queue only ever holds things that need you.

**This depends on Decision 2.** If Decision 2 is B, clerk-approved items
leave immediately anyway, and this hardly matters. If Decision 2 is A,
choose B here, or an all-clerk-approved batch would sit waiting for no
reason.

> **Aryaman's call:** _______________

### Decision 4: should the vector store wait for fact review? (new, 2026-09-28)

**Your idea:** first store the sentence. Then branch it to two workers
running side by side. One makes facts (triplets) for the graph. The other
makes chunks for the vector store.

**What happens today (checked in the code):**

- The vector store **is** written. For each approved highlight, the text
  is split into sentence-sized chunks, embedded and saved.
- Highlights with no problems flagged are written straight away. But a
  **flagged** highlight is only written **after its facts are approved**.
  While its facts wait for you, it isn't searchable either, even though
  you already approved the text itself at the intake check.
- The embeddings are made **one chunk at a time**, one call per chunk.

**The options:**

- **A. Keep it as today.** Vector chunks for flagged highlights wait for
  fact review.
  - `+` Everything about a sentence arrives at the same moment.
  - `-` Search is held back by fact review, for no real safety benefit,
    because the text was already approved.
- **B. Parallel workers, your idea.** Once the text is approved and split
  into sentences, the vector worker chunks and embeds straight away, **in
  batches**. Obsidian notes count as approved already, since you wrote
  them. The fact worker runs on its own track through fact review.
  - `+` Search works as soon as the text is approved. The two stores stop
    blocking each other. Embeddings are batched, not one call per chunk.
    Each worker can fail and retry on its own.
  - `-` For a while, a sentence can be searchable before its facts are in
    the graph. If you reject a sentence's facts, its vector chunks stay,
    because they were stored from approved text. That is probably
    correct, but it's a behaviour change.
- **C. B, but vector chunks are removed if the fact review rejects the
  whole sentence as a misreading.**
  - `+` Keeps the two stores consistent.
  - `-` It couples them again, and needs a clean-up path.

**Recommended: B.** The text approval is the right gate for search. Fact
review is about whether the LLM understood the sentence, not whether the
sentence should be findable. Batched embedding also follows your "never
one at a time" rule.

> **Aryaman's call:** _______________

## At a glance

| # | Decision | Depends on |
|---|---|---|
| 1 | What closes a batch | nothing |
| 2 | Does one slow item hold up the batch? | nothing |
| 3 | Clerk-approved items: same lane or separate? | Decision 2 |
| 4 | Vector store: wait for facts, or a parallel worker? | nothing |

## Where in the code

All paths are under `gateway/src/gateway/ingestion/`.

- **Run rules today:** `coordinator/stages.py` (`LEGAL_TRANSITIONS`). Items
  loop `INTAKE_ITEM → INTAKE_ITEM` and proposals loop
  `PROPOSAL_REVIEW → PROPOSAL_REVIEW`, with one `INTAKE_BARRIER` between
  intake and capture. Batching adds new stages and transitions here.
- **Ledger:** `coordinator/state.py`, for example the
  `intake_publications` table. The new holding-area records go here.
- **Retry per destination:** `dispatch.py`.
- **Prior art for staged steps:** `sources/page_scanner/`, with per-page
  status in `page_scanner/store.py`.
- **Vector writing today:** `consumers/vector_consumer.py`.
  - `VectorConsumer.consume()` refuses anything not `approved` or
    `not_required`, so it is gated on fact review.
  - It chunks with `vector/chunking.py` `sentence_chunks()`.
  - It calls `embedding_client.embed()` once per chunk in a loop.
  - It writes with `store.upsert_batch()` to the `knowledge` collection.
  - Decision 4B means moving this before fact review and batching the
    embed calls.
- **Where text approval happens:** `coordinator/gates.py`
  `ContentApprovalGate` (see A4).

## Aryaman's comments

Add your calls on Decisions 1–4 above, or push back on the recommended
defaults.
