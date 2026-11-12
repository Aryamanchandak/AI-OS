Read CLAUDE.md and spec.md before writing any code.
Phase 0 is complete and validated. We are doing Phase 1: the MVP processor and review cockpit.

Build exactly what is listed below. Nothing else.

PROCESSOR (process.py + core/):

core/images.py
- load_image(path) → PIL Image, RGB, EXIF-corrected
- Supports JPEG, PNG, HEIC (via pillow-heif)
- Computes and returns file_hash (sha256 of raw bytes)
- Optional downscale: if long edge > 2500px, resize preserving aspect ratio

core/ocr.py
- ocr_page(image_path) → list of dicts: {text, confidence, bbox}
  where bbox is [x, y, w, h] in image pixel coords
- Uses ocrmac. Returns results in Vision's reading order.

core/detect.py
- yellow_mask(image_rgb, hsv_params=None) → binary mask (numpy array)
  hsv_params defaults to H∈[20,35] S>80 V>120; override per batch via CLI arg
- Morphological close to fill stroke gaps

core/store.py
- SQLite schema exactly as in spec §4 (pages + passages tables)
- init_db(db_path) — creates tables if not exist
- insert_page(...) → page_id; skips if file_hash already exists (dedup)
- insert_passage(page_id, ...)
- get_pages(batch=None, status=None) → list
- get_passages(page_id) → list
- update_passage(id, edited_text)
- update_page_status(id, status)

process.py (CLI entry point)
- Args: --inbox, --batch, --author (optional), --db (default data/processed.db), --hsv (optional, e.g. "25,100,130")
- Per-image try/except: log failures to a retake list, continue batch
- Pipeline per image: load → dedup check → OCR page → build mask → intersect words with mask → group into passages → store
- Intersection: word bbox overlaps mask; use a small upward pad (10% of word height) since highlighter drifts below glyphs
- Grouper: walk kept words in reading order; same passage if gap to next word < 1.5x median line-height; new passage on larger gap
- De-hyphenate: word ending in '-' at a line boundary joins the next word
- At end: print retake list (files that errored)
- Status for all pages: 'new'

COCKPIT (server.py + static/):

server.py (FastAPI)
Endpoints exactly as in spec §7:
  GET  /                        → serve static/index.html
  GET  /api/pages?batch=...     → list pages with their passages
  POST /api/page/{id}/save      → {passages:[{id, edited_text}], page_number, status}
                                   updates DB + flushes to markdown immediately
  GET  /static/<file>           → serve static files

core/export.py
- append_or_update_page(page_id, batch, author, passages, page_number, output_dir)
  Writes to data/output/<batch>.md
  Format exactly as spec §9: blockquote per passage, "— p.N" if page_number set
  If page_id already exists in the file, overwrite that block in place (not append)

static/index.html + review.js + review.css
- Split screen: image left, passages right
- Loads GET /api/pages?batch=<current_batch> on open
- Opens to first page where status='new'
- Left pane: page image with passage bbox overlays (draw with canvas or CSS)
- Right pane: one textarea per passage, pre-filled with ocr_text
- Header: batch name, counter (N / total), page number input field
- Keyboard shortcuts (fire only when focus not in textarea, except Cmd+Enter):
    Cmd+Enter → POST /api/page/{id}/save with status='reviewed', advance to next
    →         → advance without saving (page stays 'new')
    ←         → go to previous page
    Tab       → focus next textarea
    d         → POST save with status='discarded', advance
    f         → POST save with status='retake', advance
- ← on an already-reviewed page loads it for re-editing; re-saving rewrites markdown block

OUT OF SCOPE FOR PHASE 1 — do not implement:
- Quality gate (blur/glare/confidence scoring)
- Low-confidence word highlighting in the cockpit
- Per-batch color sampling UI (click to pick color)
- Mouse-drag box fallback
- Page number field auto-population
- Readwise CSV export

Exit condition: process.py runs on the Phase 0 inbox without crashing, inserts pages and passages into the DB, and the cockpit opens in a browser showing the first unreviewed page with its image and editable passages. Cmd+Enter on a page writes a block to data/output/<batch>.md and advances. Stop there and show me:
- The DB row count (pages and passages)
- The first few lines of the generated markdown file
- Any errors encountered

Do not proceed to Phase 2.