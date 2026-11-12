"""Phase 0 de-risk spike — diagnostic only, no DB, no server.

Iterates over every image in data/inbox/ and, per image, prints:
  1. filename + loaded size after EXIF correction (HEIC via pillow-heif)
  2. full-page OCR: LiveText word tokens (the pipeline) + a Vision line pass
     (confidence calibration only) — each (text, confidence, bbox) tuple
  3. yellow mask (HSV threshold) written to spike/masks/<filename>.png
  4. Laplacian variance (blur score)
  5. word-box / yellow-mask intersection dry-run (kept words + confidence)
  6. passage-grouper dry-run (reading-order + vertical adjacency)

Ends with a summary table: filename | blur | total_words | kept_words | passages.

Run:  .venv/bin/python spike/spike.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

import ocrmac.ocrmac as ocrmac

# HEIC support must be registered before PIL can open .heic (iPhone default).
register_heif_opener()

# ── Tuning knobs (Phase 0 calibrates these on real photos) ──────────────────
YELLOW_LOWER = np.array([20, 80, 120])   # HSV, OpenCV scale H∈[0,179]
YELLOW_UPPER = np.array([35, 255, 255])
MASK_CLOSE_KERNEL = 7                     # morphological close to solidify strokes

# Highlighter ink drifts *below* the glyphs, so pad the word box DOWNWARD to
# reach the yellow that sits under the text. (Spec §5 phrases this as "bias the
# pad up" framed against the mask; padding the word box down is the equivalent.)
# Expressed as a fraction of the word's own height.
WORD_PAD_DOWN_FRAC = 0.35
WORD_PAD_UP_FRAC = 0.10
KEEP_OVERLAP_FRAC = 0.10                  # keep word if >=10% of its box is yellow

# Passage grouping: a new passage starts when the vertical centre gap to the
# previous kept word exceeds this many line-heights.
PASSAGE_GAP_LINEHEIGHTS = 1.5

INBOX = Path(__file__).resolve().parent.parent / "data" / "inbox"
MASKS = Path(__file__).resolve().parent / "masks"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".bmp"}


def load_image(path: Path) -> Image.Image:
    """Open (incl. HEIC), apply EXIF orientation, return RGB PIL image."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)   # iPhone stores rotation as metadata
    return img.convert("RGB")


def yellow_mask(rgb: np.ndarray) -> np.ndarray:
    """Binary yellow mask from an RGB numpy array (not BGR)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, YELLOW_LOWER, YELLOW_UPPER)
    kernel = np.ones((MASK_CLOSE_KERNEL, MASK_CLOSE_KERNEL), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def blur_score(rgb: np.ndarray) -> float:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def word_pixel_box(bbox, w: int, h: int) -> tuple[int, int, int, int]:
    """Vision normalized (x,y,w,h) → padded pixel box (x1,y1,x2,y2)."""
    x1, y1, x2, y2 = ocrmac.convert_coordinates_pil(bbox, w, h)
    box_h = y2 - y1
    y1 -= box_h * WORD_PAD_UP_FRAC        # small pad up
    y2 += box_h * WORD_PAD_DOWN_FRAC      # bias pad down toward the highlight
    x1i = max(0, int(round(x1)))
    y1i = max(0, int(round(y1)))
    x2i = min(w, int(round(x2)))
    y2i = min(h, int(round(y2)))
    return x1i, y1i, x2i, y2i


def overlap_fraction(mask: np.ndarray, box: tuple[int, int, int, int]) -> float:
    """Fraction of the (padded) word box covered by yellow."""
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        return 0.0
    sub = mask[y1:y2, x1:x2]
    if sub.size == 0:
        return 0.0
    return float(np.count_nonzero(sub)) / float(sub.size)


def group_passages(kept: list[dict], line_height: float) -> list[list[dict]]:
    """Walk kept words in Vision reading order; split into passages on a
    vertical centre gap larger than PASSAGE_GAP_LINEHEIGHTS line-heights."""
    if not kept:
        return []
    threshold = PASSAGE_GAP_LINEHEIGHTS * max(line_height, 1.0)
    passages: list[list[dict]] = [[kept[0]]]
    for prev, cur in zip(kept, kept[1:]):
        gap = abs(cur["cy"] - prev["cy"])
        if gap > threshold:
            passages.append([cur])
        else:
            passages[-1].append(cur)
    return passages


def passage_text(words: list[dict]) -> str:
    """Join words, de-hyphenating line-break hyphens (under-\\nstand → understand)."""
    out = ""
    for i, wd in enumerate(words):
        t = wd["text"]
        if i == 0:
            out = t
        elif out.endswith("-"):
            out = out[:-1] + t          # de-hyphenate
        else:
            out += " " + t
    return out


def process(path: Path) -> dict | None:
    print("=" * 72)
    print(f"IMAGE: {path.name}")
    try:
        pil = load_image(path)
    except Exception as e:  # per-image isolation even in the spike
        print(f"  !! FAILED to load: {type(e).__name__}: {e}")
        return None

    w, h = pil.size
    print(f"  loaded size after EXIF: {w} x {h}")
    rgb = np.asarray(pil)

    # 2. Full-page OCR.
    # Word boxes are the spine of the design (intersect words with the mask).
    # Empirically, ocrmac's *Vision* path returns LINE-level boxes (unit is
    # ignored for Vision), so the word-box pipeline uses *LiveText* tokens.
    # We ALSO run a Vision pass purely to surface its line-level confidence —
    # Phase 0 needs to see whether confidence actually varies on real photos
    # before the quality gate (§6) leans on it. (Both engines returned 1.00 on
    # crisp synthetic text; the real signal only shows up on blurry photos.)
    try:
        annotations = ocrmac.OCR(pil, framework="livetext", unit="token").recognize()
    except Exception as e:
        print(f"  !! LiveText OCR FAILED: {type(e).__name__}: {e}")
        return None
    print(f"  LiveText word tokens: {len(annotations)}")
    for text, conf, bbox in annotations:
        print(f"    {conf:.2f}  {bbox}  {text!r}")

    # Vision line-level pass (confidence calibration only — not the pipeline).
    try:
        vision_lines = ocrmac.OCR(pil).recognize()
        print(f"  Vision lines (confidence calibration): {len(vision_lines)}")
        for text, conf, _ in vision_lines:
            print(f"    conf={conf:.2f}  {text!r}")
    except Exception as e:
        print(f"  .. Vision pass failed (non-fatal): {type(e).__name__}: {e}")

    # 3. Yellow mask → PNG for eyeballing
    mask = yellow_mask(rgb)
    yellow_px = int(np.count_nonzero(mask))
    mask_path = MASKS / f"{path.stem}.png"
    cv2.imwrite(str(mask_path), mask)
    print(f"  yellow pixels: {yellow_px} ({100*yellow_px/mask.size:.2f}% of image)"
          f"  → mask: {mask_path.relative_to(INBOX.parent.parent)}")

    # 4. Blur score
    blur = blur_score(rgb)
    print(f"  blur (Laplacian var): {blur:.1f}")

    # 5. Word-box / mask intersection dry-run
    kept: list[dict] = []
    print("  -- kept words (box overlaps yellow) --")
    for text, conf, bbox in annotations:
        box = word_pixel_box(bbox, w, h)
        frac = overlap_fraction(mask, box)
        if frac >= KEEP_OVERLAP_FRAC:
            cy = (box[1] + box[3]) / 2.0
            kept.append({"text": text, "conf": conf, "box": box, "cy": cy})
            print(f"    KEEP  overlap={frac:.2f}  conf={conf:.2f}  {text!r}")
    print(f"  kept {len(kept)} / {len(annotations)} words")

    # 6. Passage grouper dry-run
    if kept:
        heights = [b["box"][3] - b["box"][1] for b in kept]
        line_height = float(np.median(heights))
    else:
        line_height = 0.0
    passages = group_passages(kept, line_height)
    print(f"  -- passages ({len(passages)}) --")
    for i, words in enumerate(passages, 1):
        min_conf = min(wd["conf"] for wd in words)
        print(f"    [{i}] (min_conf={min_conf:.2f}) {passage_text(words)!r}")

    return {
        "name": path.name,
        "blur": blur,
        "total_words": len(annotations),
        "kept_words": len(kept),
        "passages": len(passages),
    }


def main() -> int:
    MASKS.mkdir(parents=True, exist_ok=True)
    if not INBOX.exists():
        print(f"No inbox directory at {INBOX}", file=sys.stderr)
        return 1

    images = sorted(p for p in INBOX.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not images:
        print(f"No images found in {INBOX}.")
        print("Drop ~10 real photos (1-2 deliberately sideways) into data/inbox/ "
              "and re-run.")
        return 1

    rows = []
    for path in images:
        row = process(path)
        if row:
            rows.append(row)

    # Summary table
    print("=" * 72)
    print("SUMMARY")
    print(f"{'filename':<32} {'blur':>10} {'words':>7} {'kept':>6} {'passages':>9}")
    print("-" * 72)
    for r in rows:
        print(f"{r['name']:<32} {r['blur']:>10.1f} {r['total_words']:>7} "
              f"{r['kept_words']:>6} {r['passages']:>9}")
    if rows:
        blurs = [r["blur"] for r in rows]
        print("-" * 72)
        print(f"blur range: {min(blurs):.1f} – {max(blurs):.1f}   "
              f"(images processed: {len(rows)}/{len(images)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
