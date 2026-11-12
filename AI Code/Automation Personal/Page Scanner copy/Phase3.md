Read CLAUDE.md and spec.md before writing any code.
Phase 2 is complete and in daily use. We are doing Phase 3.

DRAG-BOX FALLBACK:

In the cockpit left pane, enable mouse drag to draw a selection box over the page image:
- On mousedown: record start coords (relative to image)
- On mousemove: draw a live rubber-band rect overlay
- On mouseup: send POST /api/ocr-box {image_path, bbox:[x,y,w,h]} to server

server.py: POST /api/ocr-box
- Takes image_path and bbox
- Intersects bbox against the page's existing OCR words (already stored — do not re-OCR)
- If no words overlap (sparse region, or the bbox is on a pen-underlined section with no OCR coverage), fall back to ocrmac on just that crop
- Returns {text, passage_id} where passage_id is the newly inserted passages row

Cockpit: on response, insert a new editable textarea below the existing passages for that page, pre-filled with the returned text. It behaves identically to auto-detected passages — Cmd+Enter saves it.

This handles: missed highlight regions, and legacy pen-underlined pages (drag the box over the underlined text, get the OCR, type-to-fix if needed).

PAGE NUMBER CAPTURE:
- The page number input field in the cockpit header already exists (Phase 1).
- Make it actually save: include page_number in the POST /api/page/{id}/save payload and store it in pages.page_number.
- The markdown export already uses it (spec §9 "— p.N") — confirm it works end to end.

BOOK METADATA:
- Add author field to the cockpit header (editable text input, saves on Cmd+Enter with the page).
- Store in pages.author (column already exists).
- Use in markdown export header line (*Author Name*) if set.

OUT OF SCOPE — do not implement:
- Readwise CSV
- Auto color detection
- Two-page spread splitting

Exit condition: drag a box over a region the processor missed on a real page, confirm the new textarea appears with correct OCR text. Confirm page numbers appear in the markdown output as "— p.N". Stop and report. Do not proceed to Phase 4 without explicit instruction.