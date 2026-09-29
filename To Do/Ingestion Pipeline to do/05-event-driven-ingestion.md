# 05: Ingestion That Starts by Itself

Stage B, **last**. It needs plan 02's holding areas first.

## The idea, in your words

> *"The idea was to make ingestion surface driven instead of just cron
> jobs or human run, but we want to make sure that the parts are
> separated because if it is surface detecting and running, it should not
> ingest one fact at a time — that is too expensive."*

So there are two separate jobs:

1. **Noticing.** Something (the Obsidian vault, the drop folder, later an
   agent) notices that something changed, and drops it in the waiting
   area. That's all it does.
2. **Processing.** Extraction, the clerk, review and storage run **in
   batches** when a batch closes. They never run once per event.

"Something changed → immediate LLM call" never happens.

## Why it has to wait for 02

Without 02's waiting area and batch-closing rule, an event has nowhere to
go except an immediate one-item run, which is exactly what we're
avoiding.

## Rules already settled

- An event only changes **when** something is noticed. It never skips the
  ledger, the review or the clerk.
- **No LLM calls per event.** Events fill the waiting area, and processing
  runs per batch.
- **Rapid repeats collapse into one.** Saving the same note ten times in a
  few seconds counts as one change.
- This is why 02 leans towards "close a batch on count or timer".

## Open questions (answer once 02 is settled)

1. **What watches for changes first?** Recommended: a simple file watcher
   on the drop folder and the vault. An Obsidian plugin later, if ever.
2. **Same waiting area as everything else, or a separate lane?**
3. **Bursts:** what's the cap if 500 files are dropped at once?
4. **Where does the watcher run:** inside Gateway, or as its own small
   background worker?

## Done when (rough; firm up after 02)

- Saving a note 10 times in 5 seconds creates **one** waiting item.
- 50 events cause **zero** LLM calls until the batch closes. After that,
  they cause one call per batch, not one per event.
- No event can store anything without going through normal review.

## Where in the code

- Waiting area and batch rules: from plan 02 (`coordinator/stages.py`,
  `coordinator/state.py`).
- Folders to watch: `drop_folder` and `vault_path` in
  `gateway/src/gateway/ingestion/config.py`. After A4, the drop folder is
  whatever you set in the app.
- Duplicate protection already exists: the ledger deduplicates by content
  hash. Debouncing stops the extra work before it even gets there. Key
  it on path plus content hash.
- A possible watcher library is `watchfiles`.
- Batched extraction: `pipeline.py` `_extract_pending()` and
  `extract_highlights`. Test it with a counting fake `ChatClient`.
- The only way to store anything should stay review resolution. No event
  path may call `dispatcher.dispatch()` directly.

## Aryaman's comments

