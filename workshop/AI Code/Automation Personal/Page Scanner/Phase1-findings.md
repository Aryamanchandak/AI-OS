# Phase 1 — Build & Findings

Build: MVP processor (`process.py` + `core/`) and review cockpit (`server.py` + `static/`).
Run: `.venv/bin/python process.py --inbox data/inbox --batch "Atomic Habits" --author "James Clear"`
over the 13 real photos in `data/inbox/` (IMG_7742–7754, Atomic Habits, yellow highlighter).
Result: **13/13 processed, 0 errored, empty retake list. 13 pages / 25 passages in the DB,
all status='new'.** Cockpit serves the queue and the full save → markdown-flush loop works.
Exit condition met. Did **not** proceed to Phase 2.

## Verdict (one line)

The Phase 0 spike pipeline is now production code with a passage **noise floor** that removes
the facing-page junk flagged in Phase 0 §4; the core loop (process headless → review instant)
is whole and the markdown durability path is verified end-to-end.

---

## What got built

### Processor — `process.py` + `core/`
- `core/images.py` — `load_image` (open incl. HEIC, `exif_transpose`, RGB, downscale long edge
  to ≤2500px) and `file_hash` (sha256 of raw bytes, the dedup key).
- `core/ocr.py` — `ocr_page` via `ocrmac` **LiveText tokens** (`framework="livetext",
  unit="token"`); returns `{text, confidence, bbox[x,y,w,h] in pixels}` in Vision reading order.
- `core/detect.py` — `yellow_mask` (HSV `inRange`, default H∈[20,35] S>80 V>120, morph-close
  kernel 7); `hsv_params` overrides the lower floor via the CLI `--hsv`.
- `core/store.py` — SQLite schema exactly per spec §4; `init_db`, `insert_page` (returns None on
  `file_hash` collision → idempotent skip), `insert_passage`, `get_pages`, `get_passages`,
  `update_passage`, `update_page_status`, `update_page_number`.
- `core/export.py` — `append_or_update_page`: writes `data/output/<batch>.md`; each page is one
  block delimited by `<!-- page:<id> -->` … `<!-- /page:<id> -->` so re-save rewrites in place;
  blockquote per passage with `— p.N`; skips empty `edited_text`.
- `process.py` — CLI (`--inbox --batch --author --db --hsv`); per-image try/except → retake
  list; pipeline load → dedup → OCR → mask → intersect → group → noise floor → store.

### Cockpit — `server.py` + `static/`
- FastAPI: `GET /`, `GET /api/pages?batch=`, `POST /api/page/{id}/save`, `GET /api/image/{id}`,
  `/static/*`.
- `/api/image/{id}` serves the **processed** (EXIF-corrected + downscaled) image so passage
  bboxes map 1:1 onto displayed pixels — no client-side EXIF guesswork.
- `static/` — split screen (image + canvas overlay left, one textarea per passage right),
  paper/amber editorial theme (Fraunces + DM Sans + Newsreader). Resumes to first `status='new'`.
  Keyboard: `⌘↵` accept+advance (works in textarea), `→` skip, `←` back (editable), `Tab` next
  field, `d` discard, `f` retake — single-key shortcuts fire only outside text fields.

---

## Findings

### 1. Passage grouper — line-height must be measured from the PADDED box ✅ (the key fix)
The spike's grouping quietly depended on a detail the spec prose doesn't state. Measured on
IMG_7754 (157 kept words, processed size 1875×2500):
- within-paragraph line-to-line centre gaps run **~50–96px**;
- median **unpadded** glyph-box height is only **~49px** → a 1.5× threshold (73.5px)
  over-splits a continuous highlight into one passage **per line** (observed: 9 passages where
  the spike got 3).
- The down-bias pad (`WORD_PAD_DOWN_FRAC=0.35`, up 0.10) inflates height to ~1.45×49≈71px →
  threshold ~106px, which **bridges the 96px line gaps while still splitting genuine block
  jumps** (the real gaps were 419px and 466px). This reproduces the validated spike result.
- **Result:** IMG_7754 → exactly **3 clean passages**, matching the Phase 0 golden expectation.

### 2. Passage noise floor — removes the Phase 0 §4 junk ✅
Phase 0 §4 documented IMG_7754 emitting 3 clean + 3 garbage passages from facing-page bleed on
the **left edge**. Two tunable knobs (defaults below) eliminate it:
- `EDGE_MARGIN_FRAC = 0.06` — drop a word whose box horizontal centre falls in the outer 6% of
  image width. This (not a min-words floor) is what kills the bleed: the worst junk fragment was
  **8 words**, so length alone wouldn't catch it; it's a side-edge phenomenon.
- `MIN_PASSAGE_WORDS = 2` — drop passages shorter than 2 words after grouping.
- **Result:** all 3 junk fragments dropped, 3 clean survive. No clean passage on any of the 13
  images was lost to the edge filter (frame-filling single-page shots keep body text well inside
  the outer 6%).

> Scope note: these two knobs are the one deliberate deviation from `Phase1.md` ("build nothing
> else"). They are in neither its out-of-scope nor its big-subsystem lists, and the newer,
> user-authored `Phase0-findings.md` §4 explicitly assigns both to Phase 1. Implemented as
> conservative, tunable defaults so they can be vetoed. **Awaiting user sanction.**

### 3. Per-batch passage counts (this run)
```
IMG_7742:1  7743:1  7744:1  7745:1  7746:7  7747:1  7748:1
7749:1  7750:1  7751:2  7752:1  7753:4  7754:3        total 25
```
IMG_7746's 7 are all substantive highlighted paragraphs (20–50 words each, a page on
compounding). OCR has mundane misreads inside them ("feat on given counts for lot") — exactly
the type-to-fix case the cockpit exists for, not a grouping defect.

### 4. Idempotency / dedup ✅
Re-running the same inbox: `inserted: 0  skipped(dedup): 13  errored: 0`. `file_hash` UNIQUE
skips the whole image (page + passages), so reprocessing is safe.

### 5. EXIF + image serving ✅
All 13 still arrive sideways (orientation=6) and `load_image` rights them. Because `/api/image`
re-runs `load_image`, the served image and the stored bboxes share one coordinate space — the
canvas overlay needs only a single uniform scale (`clientWidth / naturalWidth`).

### 6. Markdown durability — verified end-to-end ✅
Via the live API: accept writes the page block and flushes markdown immediately; back-nav
re-save **rewrites the same block in place** (verified 1 block, not 2); cleared passage fields
vanish; discard/retake write an empty keyed block (no quotes contributed). Page numbers persist
to the DB and render as `— p.N`.

### 7. Quality-gate columns stay NULL (as designed)
`blur_score`, `glare_score`, `conf_ratio` exist in the schema (§4) but are not populated in
Phase 1. Consistent with Phase 0 §3/§5: confidence is pinned ~1.00 and blur is uncalibrated, so
neither is a usable gate signal yet — that's Phase 2's problem and needs a known-bad photo.

---

## Known limitations / not done (Phase 1 scope)
- **No quality gate** — no page is auto-flagged `retake`; the retake list only contains files
  that *errored* (none did).
- **No low-confidence word flagging, no in-cockpit color sampling, no drag-box, no page-number
  auto-population, no Readwise export** — all deferred to later phases.
- **HEIC path still untested** — every sample is JPG (carried over from Phase 0 §6). The branch
  is present but unexercised; first real `.heic` drop is the validation.
- **Browser visual click-through not auto-verified** — no Playwright/Chromium in the env. All
  server endpoints and the save/flush/re-save/discard cycle were validated via the API; the
  cockpit's live rendering should be eyeballed once by hand.
- **`--hsv` override unexercised** — single yellow ink (Phase 0 §2) meant the default range
  sufficed for all 13; the CLI override path is coded but not run against a real lighting shift.

## How to run
```bash
# process an inbox
.venv/bin/python process.py --inbox data/inbox --batch "Atomic Habits" --author "James Clear"

# launch the cockpit
.venv/bin/python -m uvicorn server:app --port 8123
# → open http://127.0.0.1:8123
```

## Tuning knobs (all in `process.py`)
| knob | value | role |
|---|---|---|
| `WORD_PAD_DOWN_FRAC` / `WORD_PAD_UP_FRAC` | 0.35 / 0.10 | reach the ink below glyphs; also sets effective line-height |
| `KEEP_OVERLAP_FRAC` | 0.10 | keep a word if ≥10% of its padded box is yellow |
| `PASSAGE_GAP_LINEHEIGHTS` | 1.5 | new passage when the vertical gap exceeds this × line-height |
| `EDGE_MARGIN_FRAC` | 0.06 | drop facing-page edge bleed |
| `MIN_PASSAGE_WORDS` | 2 | drop sub-2-word fragments |
| `MAX_LONG_EDGE` (images.py) | 2500 | downscale cap |

Regression check when tuning: the spike harness + IMG_7754's **3-clean** target.
