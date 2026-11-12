# Phase 0 — Spike Findings

Run: `.venv/bin/python spike/spike.py` over 13 real photos in `data/inbox/`
(IMG_7742–7754, Atomic Habits, yellow highlighter).
Result: **13/13 processed, no crashes, summary table printed, 13 mask PNGs written.**
Exit condition met. Did **not** proceed to Phase 1.

## Verdict (one line)

Core loop validated on clean close-up single pages (EXIF, single yellow ink,
word-box intersection, clean passages). Before Phase 1 the grouper needs a
**noise floor**; before the Phase 2 quality gate we need a **deliberately bad
photo** to calibrate — because *neither* OCR confidence *nor* blur score
currently discriminates quality.

## Input reality (this is how photos actually arrive — not test artifacts)

The user confirmed the sample set represents real capture conditions. The
processor must assume **all** of the following on every image:

- **Stored sideways.** All 13 had EXIF orientation=6 (raw 5712×4284, i.e. 90° CW).
  EXIF correction is mandatory and load-bearing, not a rare edge case.
- **Facing page bleeds into the frame.** Pages are shot from a held-open book at
  an angle; the opposite page intrudes at one edge. This is the #1 source of
  garbage passages (see below).
- **Colored sticky-note tabs** line the page edges (orange, pink, purple, blue,
  yellow). Some fall inside the yellow hue band → mask false-positives.
- **Specular glare** on the glossy page → bright blobs in the mask.
- **Two-page spreads** occur (e.g. IMG_7750), shot from farther back, smaller
  text, only header words highlighted.

## Findings

### 1. EXIF correction — ✅ definitively working, load-bearing
All 13 images stored at orientation=6; `ImageOps.exif_transpose` rotated every
one to portrait 4284×5712. OCR then read 200–380 words/image — only possible
because rotation is applied first. This is the strongest validated result.

### 2. Yellow mask — ✅ clean on the highlight; single yellow ink confirmed
- Hue analysis: **one** yellow ink, solidly in H∈[20,35] (OpenCV scale);
  78–80% of saturated-bright pixels on close-up pages land there.
- **Zero green-dominant pixels** in any image — an initial "second green
  highlighter" hypothesis was disproven with hue data (small previews fooled
  the eye). Current single-range mask is sufficient for this book/pen.
- Mask false-positives = sticky tabs (orange H 0–19; pink/purple/blue H 86+) and
  glare. **Harmless**: they sit in margins with no text, so the word-box
  intersection drops them. (Do not conflate with finding #4.)

### 3. Blur score — ⚠️ unvalidated
- Laplacian variance range **39.0 – 67.2** across all 13.
- Narrow and low, but there is **no deliberately-blurry shot** in the set. This
  only shows the score is *stable across acceptable photos* — it does NOT show
  it separates sharp from blurry. Cannot be trusted as a gate signal yet.

### 4. Passage grouper — ⚠️ THE finding that gates the design
The summary's passage counts hide a quality split. IMG_7754 (170 words kept,
79.6% yellow — a clean, heavily highlighted page) produced **6 passages:
3 clean + 3 garbage**:

```
[1] 'mored your cceed? For ur goal to sat prac-'   ← junk
[2] 'urse t for'                                    ← junk
[3] 'nnd'                                            ← junk
[4] 'mistakenly assume that ambitious goals...'     ← clean ✓
[5] 'Problem #2: Achieving a goal is only...'        ← clean ✓
[6] 'Achieving a goal only changes your life...'     ← clean ✓
```

- **Source (confirmed via original + mask):** the **facing page bleeds into the
  left edge**. OCR reads distorted 1–2 word fragments there, a few pixels
  overlap yellow, and the grouper — having **no minimum-length / min-coverage
  floor** — promotes each stray cluster to its own "passage."
- This garbage is **text in the output**, NOT filtered by the word-box
  intersection (distinct from the harmless mask FPs in #2).
- **Looks shallow / Phase-1-fixable:** a min-words-per-passage floor + an
  x-range / dominant-page crop should drop the three junk fragments while
  leaving the clean passages untouched.

### 5. OCR confidence — ⚠️ pinned, unusable as a quality signal
- LiveText word tokens: **all conf = 1.00**.
- Vision lines: mean 0.98–1.00; only rare discrete 0.50 outliers
  (IMG_7744/7746/7752/7754).
- Confidence does not vary meaningfully on real photos → cannot drive the
  Phase 2 quality gate as-is.

### 6. HEIC path — untested
Code present (`pillow-heif` registered) but every sample was JPG, so the HEIC
branch never executed. Unvalidated.

## Implications for the next phases

- **Phase 1 (processor + cockpit):** add a passage **noise floor**
  (min words and/or min total yellow-overlap per passage) and a **crop to the
  dominant page** (drop the facing-page edge strip) before grouping. Without
  these, even clean pages emit junk passages.
- **Phase 2 (quality gate):** both intended signals are currently weak —
  confidence is pinned at 1.00, blur is uncalibrated. The gate design needs a
  **known-bad (blurry/glare-ruined) photo** to set thresholds against, and may
  need a signal beyond confidence (e.g. blur + kept-word coherence / fragment
  ratio). The 3-junk/3-clean split in #4 suggests a **fragment-ratio** signal
  (share of passages below the word floor) could itself flag a bad capture.
- The single-yellow-ink result means **per-batch color sampling (Phase 2) and
  auto color detection (parked)** are not needed for this book — keep the fixed
  H∈[20,35] range unless a new pen color appears.

## Artifacts
- Mask PNGs: `spike/masks/IMG_77{42..54}.png`
- Summary table (blur / words / kept / passages): printed by the spike run.
