# Page Scanner → Unified AI OS — status check

**Written:** 2026-07-18 · analysis pass, not a change

Where Page Scanner stands relative to the target shape: UI merged into the
unified frontend, ingestion routed through `ingestion-pipeline`, storage in
`Database/`, Page Scanner reduced to a pure logic library (OCR + spelling/text
correction).

[MY COMMENTS ARE IN CAPS]

---

## The target (confirmed across docs)

Consistent across `Constitution/UNIFIED_AI_OS_PLAN.md`, Learning System's
`REDESIGN_PLAN.md`, and `ingestion-pipeline/README.md`:

- **UI** → unified `frontend/` repo
- **Ingestion** → `ingestion-pipeline/` (code)
- **Storage** → `Database/` (data only, no code)
- **Page Scanner** → pure logic: OCR, image handling, quality gating, spelling
  correction, the "edited text" correction contract — the *capability* behind
  the correction textbox, with the textbox itself rendered by the unified
  frontend

`INTEGRATION_REQUIREMENTS.md` §1.4 explicitly names `Page Scanner/server.py` +
`static/review.js` as the **reference pattern** for the ingestion-time
abbreviation/spelling review screen — so Page Scanner's correction UX is meant
to be generalized, not thrown away.

---

## Where each piece is today

**Page Scanner itself — functionally done, architecturally a monolith.**
All phases (0–4) shipped. Still contains all four concerns in one place:
`ingest.py` (drop-folder ingestion), `core/` (OCR/logic — the part that
stays), `server.py` + `static/` (the cockpit UI, ~38KB FastAPI), and
`core/publish.py` (writes into the Raw Data lake).

**Ingestion-pipeline — created 2026-07-18, already half-absorbed Page
Scanner.** The code/data split moved all pipeline code out of `Database/`
into `ingestion-pipeline/`, including copies of cockpit-adjacent modules
(`review.py`, `images.py`, `spellcheck.py`, `obsidian_sync.py`) marked
"legacy, kept for the Page Scanner OCR review UI." So spellcheck/review logic
now exists in **two repos** — ownership unresolved.

**⚠️ Broken link found (confirmed by reading the code):**
`core/publish.py:22` does `from lib.capture import capture` after putting
`Database/Raw Data` on `sys.path` — but the 2026-07-18 split removed `lib/`
from `Database/Raw Data/` (it's now
`ingestion-pipeline/src/pipeline/core/capture.py`). **Accepting a page in the
cockpit will fail with an ImportError until this is repointed.**

**Unified frontend — essentially not started.** `frontend/` is just the old
root `app.py` (Planner re-host + optional UPI mount). No Page Scanner
cockpit, no study-system screens, nothing merged yet.

**Storage — mostly in shape.** `Database/` is now data-only (bronze, chroma,
sqlite, Raw Data). One open discrepancy: `REDESIGN_PLAN.md` says
study-system's DB goes to `Database/study-system/`, but the user's inline
comment in that doc says `Database/sqlite/study_system/` — undecided on
paper, needs a decision.

---

## What "Page Scanner is ready" requires, in order

1. **Fix the broken publish import.** Repoint `core/publish.py` at
   `ingestion-pipeline`'s `capture()`. This *is* the ingestion migration:
   Page Scanner stops writing to the lake directly and hands captures to the
   pipeline like every other source.
2. **Decide ownership of review/spellcheck logic.** One copy, not two. Given
   the "OCR + spelling correction happens here" framing, Page Scanner keeps
   and exposes them as plain functions/endpoints; `ingestion-pipeline`
   deletes its legacy copies.
3. **Extract the UI contract.** The cockpit becomes JSON endpoints (page
   image, OCR text, accept/skip/discard/flag, edited-text save); the actual
   textbox/keyboard UI moves to `frontend/`. §1.4's abbreviation-correction
   screen should be the *same* screen there, since it's the same interaction
   pattern.
4. **Then** Page Scanner is what's wanted: a logic repo the ingestion
   pipeline calls for OCR + correction, no UI, no storage of its own.

## Net state

- Storage separation: done (as of 2026-07-18)
- Ingestion separation: ~50% — repo exists, Page Scanner not wired into it,
  currently broken against it
- UI unification: ~0%
- Page Scanner's logic core: the one part that's genuinely finished

**Immediate blocker:** the `publish.py` import break (step 1 above) — this
should be fixed before anything else, since right now accepting a page in
the cockpit fails outright.
