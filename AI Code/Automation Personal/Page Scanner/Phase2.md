Read CLAUDE.md and spec.md before writing any code.
Phase 1 is complete and in daily use. We are doing Phase 2.

QUALITY GATE — add to process.py pipeline (after load, before OCR):

core/quality.py
- blur_score(image_rgb) → float
  cv2.Laplacian(gray, cv2.CV_64F).var()
- glare_score(image_rgb) → float
  Fraction of pixels above V=245 in HSV that form blobs > 500px (cv2.connectedComponentsWithStats)
- quality_gate(blur, glare, conf_ratio) → bool (True = retake)
  Thresholds: blur < 80, glare > 0.04, conf_ratio > 0.3
  These are starting defaults — add a comment that they should be tuned per real photos

conf_ratio: fraction of OCR lines (from full-page OCR) with confidence < 0.5
Store blur_score, glare_score, conf_ratio in the pages table (columns already exist in schema).
Set page status='retake' if quality_gate returns True, else 'new' as before.
Retake list at end of process.py already handles this — just make sure retake-status pages appear there.

COCKPIT — add confidence flagging to existing UI:
- In the right pane, for each passage, words/spans that came from OCR lines with confidence < 0.5 should be visually marked. Simplest: render the textarea with a faint yellow-orange background on the low-confidence passage (not per-word, just the whole field). Add a small label "⚠ low confidence" above it.
- This requires storing per-passage min_conf (already in schema) and sending it in the /api/pages response.

COCKPIT — per-batch color sampling:
- Add a small "Pick color" button in the cockpit header.
- Clicking it enters pick mode: the left pane image gets cursor:crosshair, and a click on the image sends {image_path, x, y} to a new endpoint POST /api/sample-color → {h, s, v} (server samples a 5x5px region around the click, returns median HSV).
- The returned HSV is stored client-side and sent as hsv_override in future process.py runs (just display it as text the user can copy to the --hsv CLI arg for now; a full live-reprocess is Phase 4 territory).

Run the golden set (3-4 pages with known-correct text from Phase 0) through process.py and report passage extraction accuracy vs the known-correct text.

OUT OF SCOPE — do not implement:
- Mouse-drag box
- Page number capture
- Readwise CSV
- Auto color detection (no manual click needed)

Exit condition: process.py flags at least one genuinely blurry/glare photo from the inbox as 'retake', the retake list prints correctly, low-confidence passages show the warning in the cockpit, and the golden set regression passes (extracted text matches known-correct within 1-2 character edits per passage). Stop and report results. Do not proceed to Phase 3.