# A4: A Look at Every Intake Check (and the Drop Folder Setting)

> **Status 2026-10-13: comes after the breakup (plan 01).**
>
> **New finding:** the abbreviation and spelling cleanup **never runs on
> Obsidian notes**. The pipeline uses a placeholder (`NoHighlightCleanup`,
> `pipeline.py:63`) that always reports "no typos". The cleanup database
> is also empty. See F2, F3 and O3 in `00-DECISIONS.md`.

Stage A. **Start now.** New as of 2026-09-28, from your comment: *"we
will need to have an individual look at all of these gates, not just
one."*

## What this is

Before any facts are pulled out, each dropped file passes through a series
of checks ("gates"). Each gate can stop the run and wait for you. This plan
goes through them one by one: what each does, why it's there, and what
could make it faster. It doesn't cover fact review; that's A1.

Obsidian notes don't go through these gates; they are read straight into
fact extraction. These gates are only for files and photos in the drop
folder.

## The headline finding

**Every dropped file needs a manual "approve" click today, even when
nothing about it was changed.** The cleanup gate forces this on purpose,
so that no file goes through without you seeing it. That's a reasonable
safety rule, but it means a folder of 40 clean markdown files costs 40
clicks. It's probably the biggest source of friction outside fact review.

## The gates, in the order a file meets them

### 1. Book identity (photos only)

- **What it does:** the first time a folder of book-page photos is seen,
  the system guesses the book's title, author and year from the folder
  name and looks up a cover. It then asks you to confirm or correct it.
- **Why:** every highlight from those photos is filed under that book. A
  wrong title spreads to every fact.
- **How often:** once per book folder, not per photo. That's already
  cheap.
- **Could it be faster?** When the lookup is very confident (an exact
  title and author match with a cover), it could be accepted
  automatically and shown for undo. This is low priority.

### 2. Abbreviation cleanup

- **What it does:** it looks through the text for shorthand **you've
  already taught it** ("govt", "w/", "b/c"), using your remembered list,
  and proposes the full word. For each match you choose: apply once,
  apply and remember, or skip. It doesn't discover new shorthand by
  itself.
- **Why:** facts pulled from "govt" and "government" would otherwise be
  treated as different things.
- **How often:** once per match. **Remembered shorthand is still shown to
  you every time.** It's proposed again rather than applied silently.
- **Could it be faster?** Shorthand you've marked "remember" could be
  applied silently, and shown as a list you can undo. That's what
  "remember" suggests it should already do.

### 3. Spelling cleanup

- **What it does:** an LLM proposes spelling fixes (mostly OCR mistakes
  from photos), and you accept or reject each one. If the LLM is down,
  the run waits for you to retry.
- **Why:** OCR misreads ("rn" read as "m") turn into wrong facts.
- **How often:** once per proposed fix.
- **Could it be faster?** This is a natural fit for the A1 clerk. Very
  confident, one-letter OCR fixes could be accepted automatically, with
  the rest shown to you. Another option: only run it on photos, not on
  typed files.

### 4. Approve the final text (every file)

- **What it does:** it shows you the final text after cleanup. For a
  photo, you see the highlighted passages and can edit them, then
  approve, discard or "retake". For a typed file, you see the text and
  approve or discard.
- **Why:** it's the last human look before the text goes into the vault
  and on to fact extraction.
- **How often:** **every file, every time**. This is the headline finding
  above.
- **Could it be faster?** Options:
  - (a) Keep it for photos (OCR really can be wrong), but skip it for
    typed files that had no cleanup changes.
  - (b) Batch it: approve a whole folder's worth of text on one screen.
  - (c) Leave it as it is.

### 5. "Continue to fact review?"

- **What it does:** once every file has been through intake, the run
  pauses and asks if you want to continue to fact extraction and review,
  or stop there.
- **Why:** it lets you do intake now and fact review later.
- **How often:** once per run.
- **Could it be faster?** It could be made a setting ("always continue")
  instead of a question every time.

### Not a gate, but related: photo quality

The photo scanner automatically scores blur and glare, and it flags bad
photos for a retake before you ever see them. No click is needed. It's
listed here only so the picture is complete.

## The drop folder setting

**Today:** the drop folder is hard-coded to
`/Users/aryamanchandak/Desktop/AI OS INGESTION`.

**Change, as you suggested:**

1. Store the drop folder location as a setting outside the code, the same
   way the other ingestion settings are stored.
2. Add it to a small **Ingestion settings** panel in the app. The panel
   shows the current folder, has a "Change…" button, and checks that the
   folder exists and can be written to.
3. Keep your Desktop path as the default when nothing is set.
4. The same panel is a natural home for the other switches in this plan
   ("always continue", the judge worker's controls such as run now and
   pause, and so on). The judge has no off / watch-only switch (M12).

## Decisions for Aryaman

1. **Approve-every-file (gate 4):** (a) skip it for unchanged typed
   files, (b) approve a folder at once, or (c) leave it. Recommended: (a)
   now, (b) later with batching. **Note:** "every file needs a final
   approve" was a deliberate, written rule when cleanup was built
   (requirement C8-C3 in the cleanup spec, `component_8.md`). Choosing (a)
   or (b) means consciously reversing that earlier call.
   > **Aryaman's call:** _______________
2. **Remembered shorthand (gate 2):** apply it silently, with an undo
   list, instead of asking each time? Recommended: yes.
   > **Aryaman's call:** _______________
3. **Spelling (gate 3):** photos only, clerk-assisted, or unchanged?
   Recommended: photos only now, and clerk-assisted once A1 is live.
   > **Aryaman's call:** _______________
4. **"Continue to fact review?" (gate 5):** keep asking, or make it a
   setting? Recommended: a setting, defaulting to "ask".
   > **Aryaman's call:** _______________
5. **Book identity (gate 1):** auto-accept very confident matches?
   Recommended: not yet. It's once per book, so it's already cheap.
   > **Aryaman's call:** _______________
6. **Drop folder:** one folder, or allow several? Recommended: one for
   now.
   > **Aryaman's call:** _______________

## Done when

- Each gate decision above is made and, where it changes behaviour, has a
  test showing the new behaviour and a test showing the old behaviour when
  switched off.
- The drop folder can be changed from the app without editing code, and
  the next run uses the new folder.
- The crash-recovery machinery is untouched.

## Where in the code

All paths are under `gateway/src/gateway/ingestion/`.

- **All intake gates:** `coordinator/gates.py`, which has
  `BookMetadataGate`, `CleanupGate` (abbreviation, then spelling),
  `ContentApprovalGate` and `PhaseHandoffGate`.
- **Gate order:** `coordinator/coordinator.py`, where `RunCoordinator.__init__`
  builds the gate list. `_process_intake_item()` runs book identity first,
  then the others in order.
- **Why every file needs approval:** `CleanupGate.overlay()` sets
  `needs_approval=True` on every item, unconditionally. Its docstring says
  so ("C8-C3"). `ContentApprovalGate.pending()` then always blocks. Option
  (a) in Decision 1 changes this rule.
- **Book lookup:** `sources/book_metadata.py`.
- **Abbreviation and spelling:** `text_cleanup/abbreviations.py`,
  `text_cleanup/spelling.py`, and the remembered mappings in
  `text_cleanup/store.py`.
- **Photo quality:** `sources/page_scanner/quality.py`.
- **Drop folder default:** `config.py` (around line 126). The environment
  settings are read in `server.py`'s `config_from_environment()`. The
  settings panel is a new screen under `shell/src/screens/`, backed by a
  small settings route in `server.py`.

## Aryaman's comments

