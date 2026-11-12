# Highlight Grabber — Build Spec

A personal, local, Mac-only tool that turns photos of highlighted book pages into clean text, with a fast keyboard-driven review cockpit. Replaces the Readwise photo-OCR flow, minus the fingertip dragging and the page-by-page mobile tedium.

**Owner:** AC2 — **Status:** Priority 1 — **Platform:** macOS (Apple Silicon, M5)

---

## 1. The one-paragraph mental model

You read with a **yellow highlighter**. You photograph marked pages fast and sloppy with the normal iPhone camera. You dump the folder onto the Mac. A headless **processor** finds the yellow regions, OCRs them with Apple's built-in Vision engine, scores each page for quality, and writes everything to a local database. Then you open a **review cockpit** in the browser: page image on the left, editable extracted text on the right. You skim, fix anything OCR fumbled by *typing* (the page is right there), hit a key, and it advances. Accepted passages append to a per-book markdown file. That's the whole loop.

**The core design decision:** process first (slow, headless), review second (instant, precomputed). The review cockpit never waits on OCR — everything it shows is already computed. That's what makes review feel snappy instead of laggy.

---

## 2. Locked-in decisions (the "why", so we don't relitigate)

| Decision | Choice | Reason |
|---|---|---|
| Mark type | Yellow highlighter, not pen underline | Color detection is deterministic and reliable; underline detection is the hard, brittle problem we're deliberately avoiding. |
| Detection engine | Classic CV color thresholding (OpenCV) | No model needed. Instant, free, deterministic. |
| OCR engine | Apple Vision / LiveText via `ocrmac` | On-device, fast, batch-friendly, returns per-line **confidence + bounding boxes**. Beats Tesseract/EasyOCR on Mac for printed text. |
| **OCR strategy** | **OCR the whole page once, then keep words whose boxes fall inside the yellow mask** (not crop-then-OCR). | One OCR pass instead of N+1. Vision already gives word boxes, so intersecting with the mask is cheap — and it makes multi-line passages reassemble themselves in Vision's reading order (see §5). This is the spine of the design. |
| VLM / Ollama | **Not in the pipeline.** | Wrong hammer for clean printed pages. Optional escape hatch only, much later, if ever. |
| Cross-validation | None. Use Vision's confidence scores instead. | Vision doesn't hallucinate — errors are mundane misreads, not invented text. Confidence flags the suspect lines. |
| Capture | Normal iPhone camera, fast. **No scanner mode.** | Scanner mode front-loads friction onto every shot. We move QA to review-time via the quality gate. Large-print books give text-height margin. |
| Quality control | Code flags bad pages → retake list | Capture stays brain-off; the tool catches the misses. |
| OCR perfection | Not required | Split-screen + type-to-fix is the final pass. This is what lets v1 stay small. |
| Review surface | Local web app (split screen) | Best fit for image+editable-text side by side, keyboard shortcuts, and a mouse-drag fallback box. |
| Output | Per-book markdown, structured for easy Readwise-CSV export later | Keep it plain and portable. |

---

## 3. Architecture

Three stages, cleanly separated.

```
  iPhone camera roll  →  data/inbox/  (drop folder)
                              │
            ┌─────────────────▼─────────────────┐
            │  STAGE 1 — PROCESSOR (headless)    │
            │  process.py                        │
            │  load(+EXIF) → OCR page → mask      │
            │  yellow → intersect → group →      │
            │  quality-score → store             │
            └─────────────────┬─────────────────┘
                              │  writes
                       data/processed.db  (SQLite)
                              │  reads
            ┌─────────────────▼─────────────────┐
            │  STAGE 2 — REVIEW COCKPIT          │
            │  server.py + static/ (browser UI)  │
            │  split screen, keyboard triage,    │
            │  type-to-fix, drag-box fallback    │
            └─────────────────┬─────────────────┘
                              │  on accept
            ┌─────────────────▼─────────────────┐
            │  STAGE 3 — EXPORT                  │
            │  export.py                         │
            │  per-book markdown (+ Readwise CSV │
            │  later)                            │
            └────────────────────────────────────┘
```

### Project layout
```
highlight-grabber/
  spec.md                 # this file
  CLAUDE.md               # project memory / conventions for Claude Code
  pyproject.toml
  process.py              # Stage 1 entry point (CLI)
  server.py               # Stage 2 local server (FastAPI)
  static/
    index.html            # review cockpit
    review.js
    review.css
  core/
    images.py             # load, HEIC→RGB, downscale helpers
    detect.py             # yellow-region detection
    ocr.py                # ocrmac wrapper, region + full-page OCR
    quality.py            # blur / glare / confidence metrics
    store.py              # SQLite schema + read/write
    export.py             # markdown / Readwise CSV
  data/
    inbox/                # drop photos here
    processed.db
    output/               # markdown files land here
```

---

## 4. The data model (SQLite)

Keep it dead simple. Two tables.

```sql
-- one row per photo
CREATE TABLE pages (
  id            INTEGER PRIMARY KEY,
  batch         TEXT,        -- book name / capture session
  author        TEXT,        -- nullable; Readwise import wants it
  image_path    TEXT,
  file_hash     TEXT UNIQUE, -- dedup key: re-running never double-inserts (§5)
  page_number   INTEGER,     -- nullable, set in review
  blur_score    REAL,
  glare_score   REAL,
  conf_ratio    REAL,        -- fraction of low-confidence lines
  status        TEXT,        -- 'new'|'reviewed'|'discarded'|'retake'
  created_at    TEXT
);

-- one row per detected highlight region on a page
CREATE TABLE passages (
  id            INTEGER PRIMARY KEY,
  page_id       INTEGER REFERENCES pages(id),
  bbox          TEXT,        -- JSON [x,y,w,h] in image coords
  color_tag     TEXT,        -- sampled hue label; 'yellow' for now, room for more later
  ocr_text      TEXT,        -- raw Vision output
  edited_text   TEXT,        -- what you typed/confirmed; defaults to ocr_text
  min_conf      REAL,        -- lowest line confidence in this region
  accepted      INTEGER DEFAULT 0
);
```

Everything the cockpit needs is here. No re-processing during review.

**Durability rule (important):** the DB is fully regenerable from the photos — *except* `edited_text`, which is you typing and can never be recovered. So on accept, edits flush **immediately to the per-book markdown** (§9), not only to the DB, and `data/output/` lives in git or a synced folder. Losing `processed.db` should cost a reprocess, never a re-type.

---

## 5. Stage 1 — Processor (`process.py`)

CLI: `python process.py --inbox data/inbox --batch "Thinking Fast and Slow"`

Per image, wrapped in **per-image try/except** so one bad file (corrupt photo, undecodable HEIC, OCR exception) logs to the retake list and the batch keeps going — never dies at image 140 of 200.

1. **Load** (`core/images.py`)
   - Read JPEG/PNG normally; read **HEIC via `pillow-heif`** (iPhone default — this *will* bite if skipped). Convert to RGB.
   - **Apply EXIF orientation** on load. iPhone stores rotation as metadata, not baked into pixels; ignore it and pages come in sideways and silently OCR to garbage. Non-negotiable.
   - **Dedup:** compute a file hash. If it's already in `pages.file_hash`, skip — re-running on the same inbox is safe and idempotent.
   - Optionally downscale very large images to a sane working size (e.g. long edge ~2500px) for speed. Text stays well above OCR-DPI needs.

2. **OCR the whole page once** (`core/ocr.py`)
   - `ocrmac` on the full page → list of `(text, confidence, bbox)` per word/line, in Vision's reading order. Keep this list; it drives steps 3–5, the confidence gate, and the Stage 2 drag-box fallback.

3. **Build the yellow mask** (`core/detect.py`)
   - Convert to HSV. Threshold on the yellow band — **color from the per-batch sample** (§8). Morphological close to fill the stroke into solid bands.

4. **Intersect + group into passages**
   - Keep each OCR word whose box overlaps the yellow mask (use overlap fraction, with a small upward pad — highlighter drifts *below* the glyphs, so bias the pad up).
   - **Group kept words into passages.** A highlighted sentence that wraps across 3 lines produces 3 separate mask bands; this is where they reassemble. Rule: walk the kept words in Vision's reading order; words that are contiguous in that order and vertically adjacent (gap < ~1.5 line-heights) belong to one passage. A large reading-order gap starts a new passage. This cleanly separates a 3-line highlight from an unrelated highlight lower on the page.
   - De-hyphenate line breaks: a kept word ending in `-` at a line end joins the next (`under-\nstand` → `understand`).
   - Each passage stores its merged text, the union bbox (for the cockpit overlay), and `min_conf` across its words.

5. **Quality score** (`core/quality.py`) — see §6.

6. **Store** (`core/store.py`): insert the page row + its passage rows. `status='retake'` if it fails the gate, else `'new'`.

At the end: print a **retake list** — filenames that failed the gate *or* threw an error. Reshoot those, drop them back in inbox, re-run; the hash dedup means only the new/changed files get processed.

---

## 6. The quality gate (§ what flags a retake)

Cheap per-image checks. Calibrate thresholds in Phase 0 on *your* real photos — don't trust defaults.

- **Blur** — variance of the Laplacian: `cv2.Laplacian(gray, cv2.CV_64F).var()`. Low variance = soft/blurry. Flag below a tuned cutoff.
- **Glare** — fraction of near-white blown-out pixels in clustered blobs (a lamp hotspot clips to pure white and eats text). Flag above a tuned fraction.
- **OCR confidence (the real one)** — `conf_ratio` = fraction of full-page lines with confidence below ~0.5. High ratio = OCR struggling. This measures the thing you actually care about, so weight it most.
- **No-highlight-found** — page yielded zero regions but was expected to have marks → lighting probably killed the yellow. Flag.

A page is `retake` if it trips blur/glare hard, or `conf_ratio` is high. Otherwise it flows to review (where typing covers the rest).

---

## 7. Stage 2 — Review cockpit (`server.py` + `static/`)

A tiny FastAPI server serving one HTML page. This is the part you touch daily, so it has to feel good.

### Layout — split screen
- **Left pane:** the page image, scaled to fit, with detected highlight boxes drawn as overlays.
- **Right pane:** one editable textarea **per detected passage**, pre-filled with `ocr_text`. Words/lines below the confidence threshold are visually marked (e.g. faint highlight) so your eye jumps straight to what to check.
- Header: batch/book name, page counter (`7 / 41`), page-number field.

### Interaction
- **Type freely** in any textarea to fix OCR. The page image is right there for reference — this is the whole point, and the reason OCR doesn't need to be perfect.
- **Open to the first un-reviewed page** on launch (use `status`), so multi-sitting sessions resume where you left off.
- **Keyboard shortcuts** (review is keyboard-first) — but they fire **only when focus is not in a textarea**, or you'll type "s" instead of skipping. The commit key works from anywhere:
  - `Cmd+Enter` — accept all passages on this page, save, advance (works even from inside a field).
  - `→` — advance **without saving** (page stays `'new'`, returns next session). This is skip; no separate key needed.
  - `←` — go back to the previous page (editable; re-saving rewrites, not duplicates).
  - `Tab` — jump between passage fields.
  - `d` — discard (junk photo / accidental shot; status `'discarded'`, excluded from output).
  - `f` — flag for retake.
- **Editable back-nav:** `←` to a page you already accepted lets you re-edit and re-save. Accept-then-spot-a-typo will happen constantly; there must be a path back. Re-saving rewrites that page's block in the markdown (keyed by page id), it doesn't append a duplicate.
- **Save = immediate markdown flush.** Accepting writes the edited text to both the DB and the per-book markdown right then (§4 durability rule).
- **Mouse-drag fallback:** drag a box on the left image over a passage detection missed (or a legacy pen-underline page). On release, the server intersects that box against the page's existing OCR words (no re-OCR needed in the common case) and adds a new editable field. This single feature also handles the **already-underlined backlog (Option A)**: same drag, fast on a mouse, inside the batch flow.

### Endpoints (minimal)
```
GET  /                      → cockpit HTML
GET  /api/pages?batch=...   → list of pages + passages (from DB)
POST /api/page/{id}/save    → {passages:[{id, edited_text}], page_number, status}
POST /api/ocr-box           → {image_path, bbox} → returns OCR text for an ad-hoc crop
```

---

## 8. White-balance handling (the one real knob)

A hardcoded yellow threshold drifts as lighting changes. Solution, in order of effort:

- **v1 (do this):** once per batch, you click the highlighter color on one sample image in the cockpit (or pass an HSV via CLI). That centroid + a tolerance band drives detection for the whole batch. Trivial, robust, since one book/session shares lighting.
- **Later (optional):** auto-pick the most saturated hue cluster that isn't black text or white paper, and drop the manual click.

Shooting under consistent white light (your plan) makes even the v1 click rarely necessary to re-do.

---

## 9. Stage 3 — Output (`export.py`)

Per-book markdown in `data/output/`, written **incrementally on each accept** (not in a final batch step) and kept in git/synced:

```markdown
# Thinking, Fast and Slow
*Daniel Kahneman*

> The confidence people have in their beliefs is not a measure of the quality of evidence.
— p. 209

> Nothing in life is as important as you think it is while you are thinking about it.
— p. 402
```

Each page's passages write as one block keyed by page id, so re-saving an edited page (§7 back-nav) rewrites that block in place instead of appending a duplicate. Discarded/skipped pages contribute nothing.

Store cleanly enough that a **Readwise bulk-import CSV** (`Highlight, Title, Author, Note, Location`) is a ~10-line export later — `author` and `page_number` are already captured for exactly this. Readwise CSV import is the no-API path; the API push is a Phase 4 nicety, not a dependency.

---

## 10. Build phases (ship the thin slice first — on purpose)

> **Guardrail:** the failure mode here is turning a weekend tool into a cathedral. Each phase must be *usable on its own*. Do not start a phase before the previous one is in daily use. Phase 1 already beats Readwise for this use case.

### Phase 0 — De-risk spike (½ day, before any UI)
On **10 real photos you take**, confirm:
- `ocrmac` installs and OCRs a book page cleanly, **with EXIF orientation applied** (shoot a couple sideways on purpose to prove the loader rights them).
- Yellow mask + word-box intersection picks out the right words.
- The multi-line grouping rule reassembles a 3-line highlight into one passage.
- How much (if at all) a pen underline *under* the highlight actually hurts Vision OCR.
- Tune blur / glare / confidence cutoffs on these real images.
- Set aside 3–4 of these pages with hand-typed correct text as a **golden set** for later regression checks.

**Exit:** approach validated, thresholds calibrated. If OCR-through-underline is bad, note it — but the type-to-fix path covers it, so it's not a blocker.

### Phase 1 — MVP (the thing you open this week)
- `process.py`: inbox (JPEG + **HEIC**, EXIF-correct, hash-dedup, per-image error isolation) → page OCR → yellow mask → intersect → group → SQLite.
- Cockpit: split screen, editable text, resume to first un-reviewed, `Cmd+Enter`/`d`/`←`/`→`, editable back-nav, **immediate markdown flush** with title + author.
- **Not included:** quality gate, drag-box, page numbers, Readwise.
- **Done when:** you can dump a folder and walk a real book's highlights faster than Readwise ever let you.

### Phase 2 — Sloppy-capture support
- Quality gate (blur/glare/confidence) → retake list.
- Low-confidence words visually flagged in the cockpit.
- In-cockpit per-batch color sampling (replace the CLI color arg).
- Run the Phase 0 golden set as a quick regression check whenever thresholds change.

### Phase 3 — Fallback + backlog
- Mouse-drag box → intersect-against-existing-OCR → new field. (Handles missed regions **and** legacy underline pages, Option A.)
- Page-number capture + book metadata.

### Phase 4 — Optional, resist unless wanted
- Readwise CSV export, then API push.
- Underline-erase (horizontal morphology on the known crop) for any stubborn re-highlighted book (Option B hardening).
- Auto color detection (drop the manual click).

### Explicitly parked (not now)
- Handwriting / your own margin notes capture — separate problem, you said you'll type those.
- Any VLM/Ollama integration.
- Multi-book / multi-batch management UI. One batch at a time is fine.

---

## 11. Dependencies
```
ocrmac            # Apple Vision OCR (macOS only)
opencv-python     # color detection, quality metrics
pillow            # image handling
pillow-heif       # iPhone HEIC support  ← do not skip
fastapi, uvicorn  # review cockpit server
numpy
```
Plus a `CLAUDE.md` in the repo root capturing these conventions — your established high-leverage habit. Keep it short: stack, the process-then-review rule, the "each phase ships usable" rule, and the parked list.

---

## 12. First commands to run (Phase 0)
```bash
mkdir -p highlight-grabber/{core,static,data/{inbox,output}}
cd highlight-grabber
python -m venv .venv && source .venv/bin/activate
pip install ocrmac opencv-python pillow pillow-heif numpy
# drop ~10 real photos into data/inbox, then write the Phase 0 spike script:
#   - load each (incl. HEIC), HSV threshold for yellow, show detected boxes
#   - OCR each crop with ocrmac, print text + confidence
#   - print Laplacian variance (blur) per image
# eyeball the results, tune thresholds, decide go/no-go.
```

---

## 13. Capture rules (the human side)

The processor assumes a few things about how you shoot. Keep these and the code stays simple:

- **One page per photo, filling the frame.** A two-page spread shot from far away halves the resolution per page and breaks the single-page assumptions (page number, reading order). If you do catch spreads, that's a real feature to add later (split down the gutter into two pages) — but v1 assumes one page per shot. Decide now, document it, don't let it leak in silently.
- **Even white light, no glare.** Diffuse beats bright. A single harsh lamp on semi-glossy paper makes specular hotspots that eat text — the glare check will bounce those to retake, but it's faster to just avoid them.
- **Tap to focus, brace your hands.** Slight blur hurts OCR more than slightly lower resolution.
- **Don't bother with ProRAW / 48MP.** One frame-filling page is already far past OCR-DPI needs; big files just slow the batch.

---

## 14. Robustness & verification (what separates a demo from a tool you trust)

- **EXIF orientation** applied on every load (§5). The single most likely silent-failure bug.
- **Per-image error isolation** (§5): one unreadable file logs and is skipped, the batch completes.
- **Idempotent reprocessing** via `file_hash` (§4–5): re-running the inbox never duplicates rows; retakes slot in cleanly.
- **Edit durability** (§4): typed text flushes to git-backed markdown immediately; the DB is disposable.
- **Golden set** (Phase 0): 3–4 pages with known-correct text, re-run after any threshold/logic change to catch regressions. Fits how you already QA pipelines.
- **All local.** Nothing leaves the Mac — no API, no upload — which is also why Apple Vision (on-device) is the right OCR choice, not a cloud one.

---

## 15. Net change from v1 of this spec

The one architectural revision: **OCR-the-page-then-intersect-with-the-mask**, replacing crop-then-OCR. It's one pass instead of N+1 and it makes multi-line passage grouping fall out of Vision's reading order instead of needing bespoke geometry. Everything else here is robustness plumbing (EXIF, error isolation, dedup, durability, resume, de-hyphenation) — none of it changes the core loop, all of it is the difference between a weekend demo and something you hand a year of reading to. The core decisions — process-then-review, no VLM, Apple Vision, type-to-fix — are unchanged.