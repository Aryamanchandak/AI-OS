# OCR Follow-up #1 — Reconcile: accurate-line text + token boxes

> ⛔ **STATUS: ATTEMPTED 2026-07-05 — REVERTED. Do not re-attempt the geometric
> heuristic below.** Two versions were tried against `golden/check.py`
> (baseline 4/6 pass, worst 3.1%):
> 1. Passage-wide coverage rule → **2/6**. The passage's highlighted x-span spans
>    multiple lines, so it matched full page-width accurate lines and pulled in
>    un-highlighted words + adjacent sentences.
> 2. Per-line token→line band assignment → **1/6**, with duplicated/mangled text
>    ("Problem #2… Problem #2…"). LiveText token boxes and Vision line boxes are
>    **independent recognitions with non-aligning geometry** — a token's y-centre
>    lands in multiple lines' bands, so lines get selected twice and words double-
>    count.
> **Root finding:** reconciling the two recognizers needs real *fuzzy sequence
> alignment* between the token stream and the line stream (e.g. Needleman–Wunsch
> on the two text sequences), NOT any geometric band/coverage rule. That is a
> genuinely complex, error-prone piece of work. **And it isn't even the payoff
> lever here:** the baseline token text already scores 4/6, and its failures are
> *grouping* errors (dropped "I", merged "a symptom" — in `_keep_words` /
> `_group_passages`), not recognition errors. Better ROI is on grouping, or just
> leave it — token text is good. Everything was reverted; `process.py` and
> `golden/check.py` are back at baseline.
>
> ---
>
> Original plan (kept for context). Goal was: raise OCR text quality with **no new
> dependency, no network, no cost**, by sourcing passage *text* from Apple's
> Vision "accurate" pass while keeping LiveText token *boxes* for the yellow-mask
> intersection. The geometric approach below does not work — see status banner.

## Orientation (read first — the pipeline in 90 seconds)

This is "Highlight Grabber": photograph highlighted book pages → OCR the yellow
highlights → review in a web cockpit → export clean markdown to a Raw Data lake.

- **Stack:** Python 3.11, venv at `.venv/`. `ocrmac` (Apple Vision OCR),
  opencv, pillow, pillow-heif, numpy, FastAPI. SQLite at `data/processed.db`.
- **Core rule:** process first (headless, slow), review second (instant). The
  cockpit never runs OCR.
- **Flow:** `ingest.py` → `process.process_image()` (the OCR pipeline) → rows in
  `processed.db` → cockpit (`server.py` + `static/`) → on accept, `core/publish.py`
  writes markdown into the Raw Data lake.

This plan only touches the **OCR extraction step** inside `process.py` / `core/ocr.py`.
Nothing about ingest, the cockpit, or the lake changes.

## The problem this fixes

`process.py::process_image()` runs **two** OCR passes per page:

- `core/ocr.py::ocr_page()` — `framework="livetext", unit="token"` → per-**word**
  boxes. Used for (a) the yellow-mask intersection that decides *which words are
  highlighted*, and (b) the passage **text** (via `_passage_text()`).
- `core/ocr.py::ocr_lines()` — `framework="vision", recognition_level="accurate"`
  → per-**line** boxes + real confidence. Currently used **only** for the quality
  gate (`conf_ratio`) and per-passage `min_conf`.

The LiveText token recognizer has **weaker text** than the Vision-accurate
recognizer, but it's the only one giving word-level boxes. So today we both mask
*and read* from the weaker recognizer. Fix: **mask with token boxes, read words
from the accurate line pass.**

Evidence it matters: `golden/check.py` currently shows ~2/6 passages failing the
≤2-edit bar. The failures are a mix of recognition errors (this plan helps) and
grouping errors (this plan does **not** help — see Non-goals).

## Key code touchpoints (with current behavior)

- `process.py:145` `process_image()` — orchestrates a page. Already has both
  `lines = ocr.ocr_lines(pil)` (line ~160) and `words = ocr.ocr_page(pil)` (~168).
- `process.py:104` `_passage_text(words)` — joins token text, de-hyphenates.
  **This is what we replace/augment as the text source.**
- `process.py:88` `_group_passages(kept)` — groups kept tokens into passages by
  vertical-gap. **Unchanged** — grouping still runs on token boxes.
- `process.py:118` `_union_bbox(words)` — passage bounding box. Reused.
- `process.py:127` `_boxes_overlap(a, b)` and `process.py:134`
  `_passage_min_conf(union, lines, word_min)` — already overlap a passage's union
  bbox against the accurate `lines`. **This is the pattern to extend.**
- `core/store.py::insert_passage()` — stores `ocr_text` and `edited_text`
  (defaults to `ocr_text`). Keep writing the best text into both.
- `golden/check.py::extract_passages()` — mirrors the live pipeline (calls
  `ocr.ocr_page` + `_passage_text`). **Must be updated in lockstep** or it will
  test the old path.

## Design

For each grouped passage (a list of kept highlighted tokens):

1. Compute the passage's union bbox (`_union_bbox`) and its highlighted
   horizontal span `[x_lo, x_hi]` from the kept token boxes.
2. Find the accurate `lines` whose bbox vertically overlaps the passage (reuse
   the `_boxes_overlap` / `_passage_min_conf` overlap logic).
3. **Coverage decision per overlapping line:**
   - If the highlighted token span covers **≥ ~80%** of the line's width →
     the whole line is highlighted → use the **full accurate-line text**.
   - Else (partial-line highlight) → the accurate line contains un-highlighted
     words too. **Fall back to token text** for that line's portion (today's
     behavior — no worse), OR attempt a clipped alignment (see Hard Part).
4. Concatenate the chosen per-line text in reading order, de-hyphenate across
   line breaks (reuse `_passage_text`'s hyphen logic), and use that as the
   passage text.

Add this as a new function, e.g. `_passage_text_accurate(group, lines)`, and call
it in `process_image` instead of `_passage_text(group)`. Keep `_passage_text`
as the fallback path.

### The hard part (why this isn't a one-liner)

**Partial-line highlights.** A highlight often covers only part of a line
("…focus on **systems, not goals**"). The accurate pass returns the *whole* line;
the token boxes tell you which span was yellow. Clipping the accurate line to the
highlighted span requires aligning two **independent** recognitions (LiveText
tokens vs Vision lines) whose word splits differ slightly — a fuzzy match.

**Recommended v1:** don't attempt sub-line clipping. Use the ≥80%-coverage rule:
full accurate line when the highlight spans most of the line, token text
otherwise. This captures the common case (full-line highlights) with zero
alignment risk. Sub-line clipping via per-word x-position alignment is a v2 only
if partial highlights prove common and wrong.

## Implementation steps

1. In `process.py`, add `_passage_text_accurate(group, lines)` implementing the
   design above. Add a tunable `LINE_COVERAGE_FRAC = 0.8` near the other knobs
   (top of `process.py`, ~line 22).
2. In `process_image`, replace `text = _passage_text(g)` with the accurate
   variant, passing the `lines` already computed for the quality gate.
3. Mirror the change in `golden/check.py::extract_passages()` so the regression
   harness exercises the new path (it must also fetch `ocr.ocr_lines`).
4. Re-run `golden/check.py`. Inspect deltas. If overall edits **drop**, good. If
   any passage regresses, tune `LINE_COVERAGE_FRAC` or fall back to token text
   for that shape.
5. If the golden answers themselves were transcribed against the *old* output and
   are now stricter than reality, re-confirm each answer against the photo before
   treating a delta as a regression (the answers are human-verified truth, not a
   snapshot to blindly match).

## Testing / acceptance

- **Command:** `.venv/bin/python golden/check.py` (pass bar: each clean passage
  within ≤2 normalized char edits; see `PASS_EDITS` in that file).
- **Acceptance:** golden pass count **≥** current baseline (4/6 at time of
  writing) and worst-case error rate does not increase. Ideally 5–6/6.
- **Also run:** `.venv/bin/python tests/test_phase2.py` (must still pass — the
  quality-gate plumbing is independent but shares `ocr.ocr_lines`).
- **Spot-check** a real full-line highlight and a real partial-line highlight to
  confirm the coverage rule behaves.

## Non-goals (explicitly out of scope)

- **Grouping errors** (e.g. two passages merged, a word dropped by the mask).
  Those live in `_keep_words` / `_group_passages`, not the text source. The
  golden set's "a symptom" merge and dropped-"I" cases are grouping issues and
  will NOT be fixed here.
- Any network/LLM call — that's Follow-up #2 (`plans/ocr-followup-2-claude-cleanup.md`).
- Changing `MAX_LONG_EDGE` (already raised 2500→3600 in `core/images.py`).

## Cost / risk / effort

- **Cost:** none. Both OCR passes already run every page.
- **Risk:** moderate — changes the text path that `golden/check.py` guards.
  No hallucination surface (it only ever emits recognizer output). Re-baseline
  golden and confirm deltas shrink.
- **Effort:** ~half a day, mostly the coverage heuristic + golden re-baseline.
- **Ceiling:** fixes recognition errors (l↔1, dropped glyphs, weak-token text),
  bounded — does not touch grouping.

## Definition of done

- `process_image` sources passage text from the accurate line pass via the
  coverage rule; token boxes still drive masking/grouping.
- `golden/check.py` updated in lockstep and passing at ≥ baseline.
- `tests/test_phase2.py` passing.
- One-line note added to project memory
  (`.claude/.../memory/`) that #1 is done, referencing [[rawdata-wiring]].
