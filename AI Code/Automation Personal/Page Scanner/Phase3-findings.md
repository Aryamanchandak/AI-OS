# Phase 3 — Build & Findings

Build: drag-box fallback, author field, and page-number end-to-end confirmation.
Run: code-only session — no reprocess run needed (Phase 3 adds no processor changes).
Result: **drag-box endpoint wired, author editable and persisted, markdown header refreshes on
every save, page-number already wired from Phase 1 (confirmed, no changes needed).**
Exit condition not yet eyeballed — server starts clean; drag-box requires a live cockpit test.
Did **not** proceed to Phase 4.

## Verdict (one line)

All three Phase 3 requirements are code-complete: drag on the page image OCRs the crop and
inserts a live textarea; author saves with the page and propagates to the markdown header even
mid-batch; page numbers appear as `— p.N` as they did in Phase 1 (confirmed).

---

## What got built

### Drag-box fallback — `server.py` + `static/`

**Server — `POST /api/ocr-box`**
- Payload: `{page_id: int, bbox: [x, y, w, h]}` in natural (load_image) pixel coords.
- Looks up the page by `page_id`; loads the image via `images.load_image` (same EXIF-corrected +
  downscaled pipeline path — identical coordinate space as the stored bboxes).
- Crops to the bbox, OCRs the crop with `ocr.ocr_page` (LiveText tokens, reading order).
- Inserts a new `passages` row (`color_tag='drag'`, `min_conf=None`).
- Returns `{text, passage_id}`.

**Client — `static/review.js`**
- `mousedown` on `#page-img` (when not in color-pick mode): records start in natural coords,
  adds `.dragging` class (crosshair cursor).
- `mousemove` on `document`: updates drag end, redraws overlay.
- `mouseup` on `document`: clears drag state; ignores if box < 10×10px (click, not drag);
  otherwise calls `submitDragBox`.
- `submitDragBox`: POSTs to `/api/ocr-box`; on response inserts a new passage card with a blue
  "drag" tag, focuses the textarea, scrolls it into view. The card's textarea carries a
  `data-passage-id`, so `collectEdits()` includes it in every subsequent `⌘↵` save.
- `drawBoxes` extended: draws the live rubber-band rect on the overlay canvas (dashed blue,
  semi-transparent fill) during drag.
- `clientToNaturalCoords(clientX, clientY)`: uses `getBoundingClientRect()` to convert viewport
  coords to natural image pixel coords, clamped to image bounds.

**Design note — crop OCR instead of stored-word intersection:**
The spec says "intersect against existing OCR words (already stored)". Word-level boxes are not
persisted in the DB (only grouped passages are). Crop OCR covers the same two cases equally well:
missed highlight regions get the text from the crop; pen-underlined pages get the same (Vision
sees the text either way). A `words` table was considered and rejected — it would only help pages
reprocessed *after* the schema change, and adds schema + processor complexity for no practical
gain on an already-processed inbox.

### Author field — `static/index.html` + `review.js` + `review.css` + `server.py` + `core/store.py`

- `<div class="sub" id="author">` → `<input class="author-input" id="author" type="text">`
  Transparent border until hover (subtle), amber outline on focus. No visible change at rest.
- `render()` sets `els.author.value = page.author || ""`.
- `save()` reads `els.author.value.trim() || null`, includes it in the save payload, and updates
  `page.author` in local state so back-nav renders the latest value.
- `SavePayload.author: str | None` added to server.
- `store.update_page_author(db_path, page_id, author)` added (simple UPDATE).
- Save endpoint calls `update_page_author` and passes the author to `export.append_or_update_page`.
- Author input is an `<input>`, so `inAnyField()` already blocks single-key shortcuts while it
  is focused — no change needed to the keyboard model.

### Markdown header refresh — `core/export.py`

**The bug:** `_header(batch, author)` was only written when the `.md` file was first created.
Phase 2 is in daily use, so every book's `.md` already exists; setting author saved to the DB
but the header line was frozen.

**The fix:** `append_or_update_page` now locates the first `<!-- page:` marker and replaces
everything before it with a fresh `_header(batch, author)` on every save. If the file has no
page blocks yet (edge case: file exists but all pages were skipped/discarded), it rewrites the
whole file. A cleared author (empty input → `None`) removes the `*Author*` line immediately.

### Page number — confirmed, no changes

`SavePayload.page_number` → `store.update_page_number` → `export._block` `— p.N` was fully
wired in Phase 1. The `/api/page/{id}/save` endpoint already sent and stored it; the markdown
block already rendered it. Phase 3 adds nothing here.

---

## Findings

### 1. Author header was silently broken since Phase 1 ⚠️ (now fixed)
`_header(batch, author)` ran once on file creation. Any batch started before an author was typed
would show a headerless markdown file indefinitely. The fix (rewrite header on every save) is
cheap: it's a string slice at the first `<!-- page:` index with no regex.

### 2. Coordinate space for drag-box is inherited from the existing overlay ✅
Phase 1 proved that the passage bbox overlay scales correctly (`clientWidth / naturalWidth`).
The drag-box uses `getBoundingClientRect()` to convert the same viewport pixels to the same
natural-image space, then POSTs those coords. The server loads via `images.load_image` (same
EXIF + downscale), so the crop lands exactly where the user drew. No new coordinate math needed.

### 3. Color-pick and drag-box events don't conflict ✅
- Pick mode: `mousedown` on image returns early if `state.picking`; `click` fires as before.
- Drag mode: `e.preventDefault()` in `mousedown` suppresses the subsequent `click` event, so
  the color-picker click handler never fires after a drag.
- A tiny drag (< 10×10px natural coords) is treated as a click and ignored, leaving single-pixel
  clicks clean for both modes.

### 4. Drag passage survives `⌘↵` save unchanged ✅
`collectEdits()` collects every `textarea[data-passage-id]` in the passages div. The drag
passage card injects a textarea with the server-assigned `passage_id`, so it is included in the
next save with no special handling.

### 5. Empty drag crop is handled gracefully ✅
Server clamps bbox to image bounds; returns 400 if the clamped area has zero pixels. If OCR
finds no text in the crop, `text=""` is stored and the textarea is empty — user can type into it
or delete the card by clearing the field (cleared `edited_text` is skipped in export).

---

## Exit-condition status

| requirement | status |
|---|---|
| Drag a box over a missed region → new textarea with correct OCR text | ✅ code-complete; **needs one live cockpit drag to eyeball** |
| Page numbers appear as `— p.N` in markdown | ✅ already working since Phase 1 (confirmed) |
| Author saves with page + appears in markdown header | ✅ code-complete; header now refreshes on every save |

**To fully close Phase 3:** start the server, open a page in the cockpit, drag a box over a
region the processor missed (or any text), confirm the new textarea appears with the correct
OCR text, then `⌘↵` and confirm the passage appears in the markdown output.

## How to run

```bash
# cockpit (no reprocess needed — drag-box is a review-time feature)
.venv/bin/python -m uvicorn server:app --port 8123
# → open http://127.0.0.1:8123
# drag a rectangle on the page image to test the drag-box fallback
```

## Files changed

| file | change |
|---|---|
| `core/export.py` | header refresh on every save (not just file creation) |
| `core/store.py` | `update_page_author` added |
| `server.py` | `OcrBoxPayload`, `POST /api/ocr-box`, author in `SavePayload` + save endpoint |
| `static/index.html` | author `<div>` → `<input class="author-input">` |
| `static/review.js` | drag-box events + `submitDragBox`; author in `save()`; rubber-band in `drawBoxes` |
| `static/review.css` | `.author-input`, `.drag-tag`, `.image-wrap.dragging` |
