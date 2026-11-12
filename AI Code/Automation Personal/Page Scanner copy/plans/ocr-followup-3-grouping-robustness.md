# OCR Follow-up #3 — Grouping robustness (dropped & bled-in words)

> 📋 **STATUS: PROPOSED — awaiting your go/no-go.** Nothing here is built yet.
> This is the plan for the extraction-robustness work recommended after
> follow-ups #1 (reverted) and #2 (cleanup, shipped). It targets the **real
> lever**: grouping, not the text source.
>
> **Diagnosis-first by design.** #1 failed because it committed to a fix
> (geometric reconciliation) before proving the cause. This plan does the
> opposite: **Phase A measures why each word is dropped/added; Phase B only then
> applies the minimal fix; golden/check.py is the guardrail throughout.** Do not
> skip Phase A.

## Orientation (the pipeline in 90 seconds)

"Highlight Grabber": photograph highlighted book pages → OCR the yellow
highlights → review in a web cockpit → export markdown to a Raw Data lake.

- **Stack:** Python 3.11, `.venv/`. `ocrmac` (Apple Vision OCR), opencv, pillow,
  numpy, FastAPI. SQLite at `data/processed.db`.
- **Flow:** `ingest.py` → `process.process_image()` → rows in `processed.db` →
  cockpit → on accept, `core/publish.py` writes markdown to the lake.
- **Guardrail:** `.venv/bin/python golden/check.py` — 6 human-confirmed passages
  across 4 Atomic Habits pages; pass bar ≤2 normalized char edits each.

This plan touches only the **word-selection + grouping** step
(`process._keep_words` / `_group_passages`) inside `process.py` + `core/detect.py`
(the yellow mask). It does **not** touch the text source (that was #1) or the LLM
cleanup (#2).

## The problem — two concrete, reproducible failures

Baseline `golden/check.py` = **4/6** (worst error 3.1%). Both misses are grouping,
not recognition:

| Page | Golden | System output | Failure mode |
|---|---|---|---|
| `IMG_7749` | `…plateau-what **I call the Plateau** of Latent…` | `…plateau-what call Latent…` | **Dropped words** — a run of genuinely-highlighted words was not kept (17 edits) |
| `IMG_7754` | `**Achieving** a goal only changes…` | `**a symptom** Achieving a goal only changes…` | **Bled-in words** — `a symptom` from elsewhere was wrongly kept/merged in (10 edits) |

These are the two canonical directions of grouping error: **false negatives**
(highlighted words dropped) and **false positives** (un-highlighted words added).
Fixing them is the whole job.

## Key code touchpoints (current behavior)

- `process.py:65 _keep_words(words, mask, img_w)` — keeps a word if
  `_overlap_fraction(mask, padded_box) >= KEEP_OVERLAP_FRAC` (0.10) and its centre
  isn't in the outer `EDGE_MARGIN_FRAC` (0.06) of the page. **Where false
  negatives (drops) and edge false-positives are decided.**
- `process.py:45 _padded_box` — pads the word box down `WORD_PAD_DOWN_FRAC`=0.35,
  up 0.10 (ink drifts below glyphs). Under-padding → misses faint ink → drop.
- `process.py:53 _overlap_fraction` — yellow pixels / box pixels. For a run of
  small/thin words over faint ink this can dip under 0.10 and drop them.
- `process.py:88 _group_passages(kept)` — splits into passages only on a
  **vertical-centre gap** > `PASSAGE_GAP_LINEHEIGHTS`(1.5)×median-line-height.
  **No horizontal reasoning** → a stray kept word on a nearby line merges in.
- `process.py:34 MIN_PASSAGE_WORDS`=2 — drops passages shorter than 2 words
  after grouping (can silently eat a correct short highlight, or fail to eat a
  2-word false positive like "a symptom").
- `core/detect.py::yellow_mask(rgb, hsv)` — the HSV yellow mask. Under-inclusive
  mask → dropped words; over-inclusive → bled-in words. Per-batch HSV sampling
  (Phase 2) already exists as a knob.
- `golden/check.py::extract_passages()` — mirrors the pipeline; **the harness.**

## Phase A — Diagnose (measure before touching anything)

Goal: for **each** of the two failures, prove the exact cause. Write a throwaway
script `golden/diagnose.py` (do NOT wire into `check.py`) that, for a given page:

1. Runs `ocr.ocr_page` and prints, for the words in the failing region, whether
   each is even in the OCR output (rules out "recognizer never saw it").
2. For each such word, prints: its box, its **padded** box, its
   `_overlap_fraction` vs the mask, its centre-x vs the edge margins, and whether
   `_keep_words` kept it. → tells us *which gate* dropped `I / the / Plateau`.
3. For `IMG_7754`, does the same for `a` and `symptom`: were they **kept by the
   mask** (a mask false-positive — real yellow-ish pixels there), or kept-and-
   **merged by grouping** (grouped with the passage below despite a real gap)?
4. Prints the grouping decision: the per-word `_cy`, the median line-height, the
   threshold, and the gap that (failed to) split `a symptom` off.

**Exit of Phase A:** one sentence per failure naming the responsible gate, e.g.
"IMG_7749 drops `I/the/Plateau` because their overlap fraction is 0.06–0.09 < 0.10
(faint ink, under-padding)", "IMG_7754 keeps `a symptom` because the mask has a
yellow false-positive there AND the vertical gap to the passage below is
1.2×line-height < 1.5". **Only proceed once each cause is confirmed by numbers.**

## Phase B — Fix (minimal, contingent on Phase A)

Apply only the fix that Phase A's numbers justify. Candidate fixes per confirmed
cause (pick the matching one; do not apply blind):

**If drops are caused by overlap threshold / padding (likely IMG_7749):**
- Lower `KEEP_OVERLAP_FRAC` slightly (0.10 → ~0.07), OR make it **area-aware**:
  require a lower fraction for thin/small boxes (a 1-glyph "I" has few pixels, so
  fraction is noisy) — e.g. keep if `overlap_fraction >= K` **or** absolute
  yellow-pixel count exceeds a small floor.
- OR widen `WORD_PAD_DOWN_FRAC` a touch if ink consistently sits lower than 0.35h.
- Re-run golden after **each** knob change; keep only changes that don't regress
  the other 5 passages.

**If bleed-in is a mask false-positive (possible IMG_7754):**
- Tighten the yellow mask (raise HSV S/V floor) OR add a small morphological
  open to kill speckle. Trade-off: too tight re-introduces drops — golden catches
  it.

**If bleed-in is a grouping merge (possible IMG_7754):**
- Add **horizontal-gap awareness** to `_group_passages`: also split when the
  reading-order jump in x (or a line change) is large, not just vertical gap.
- OR reconsider `MIN_PASSAGE_WORDS` / a leading-orphan trim: a 2-word fragment
  far from the body is likely bleed.

**Guard rails on every change:**
- Change **one knob at a time**; re-run `golden/check.py`; record the delta.
- A fix that improves the target page but regresses another is rejected — the net
  must be ≥ baseline on all 6.

## Phase C — Validate

- `.venv/bin/python golden/check.py` → **≥ 4/6, target 6/6**, worst error rate
  does not increase.
- `.venv/bin/python tests/test_phase2.py` → still green (shares `ocr.ocr_lines`).
- `.venv/bin/python tests/test_cleanup.py` → still green (independent, but prove
  it).
- Spot-check `IMG_7746` (the excluded two-column hard case) does not get *worse*.
- If a golden answer itself turns out stricter than the photo (re-transcribe from
  the image), fix the answer — the answers are human truth, not a snapshot to
  match. Note any such change.

## Non-goals / alternatives considered (so scope stays honest)

- **Text-source reconciliation (follow-up #1)** — reverted; needs fuzzy
  token↔line alignment and doesn't fix grouping. Not here.
- **Feeding the Vision-accurate line text into the #2 cleanup call as a
  reference.** A real recognition-robustness lever, but (a) it's recognition, not
  grouping, and (b) it weakens #2's clean "model only sees the text it corrects"
  safety property. Deferred; revisit only if pure-text cleanup proves to
  hallucinate. Not in this plan.
- **difflib `SequenceMatcher` alignment** — the tractable offline version of #1;
  low ROI (token text already 4/6). Not here.

## Cost / risk / effort

- **Cost:** none (offline, no new dep, no network).
- **Risk:** moderate — edits the word-selection path the golden set guards. The
  diagnosis-first structure + one-knob-at-a-time + golden gate contain it. The
  main failure mode is a knob that helps one page and quietly hurts another —
  golden is exactly the tripwire for that.
- **Effort:** ~half a day. Phase A (diagnosis script) is most of the value; the
  fix is usually a 1–2 line knob change once the cause is known.

## Definition of done

- Phase A cause confirmed in numbers for both failures (throwaway `diagnose.py`).
- Minimal fix applied in `process.py` / `core/detect.py`, one knob at a time.
- `golden/check.py` ≥ baseline (target 6/6), `tests/test_phase2.py` and
  `tests/test_cleanup.py` green.
- One-line note to project memory that #3 is done, referencing [[cleanup-pass]]
  and [[rawdata-wiring]], recording which knob moved and the new golden score.
