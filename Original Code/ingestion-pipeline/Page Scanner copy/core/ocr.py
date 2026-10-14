# Agent guide: Wraps Apple Vision through ocrmac and returns word- or line-level text, confidence, and pixel bounding boxes.
"""Apple Vision OCR via ocrmac.

Phase 0 finding: ocrmac's default Vision path returns LINE-level boxes, but the
word-box / mask intersection that is the spine of this design needs word-level
boxes. LiveText tokens (`framework="livetext", unit="token"`) give per-word
boxes, so that is the pipeline path.
"""

from __future__ import annotations

from PIL import Image

import ocrmac.ocrmac as ocrmac


def ocr_page(pil_image: Image.Image) -> list[dict]:
    """OCR the whole page once → list of {text, confidence, bbox}.

    bbox is [x, y, w, h] in image *pixel* coordinates. Results are returned in
    Vision's reading order, which is what the passage grouper relies on.
    """
    w, h = pil_image.size
    annotations = ocrmac.OCR(
        pil_image, framework="livetext", unit="token"
    ).recognize()

    words: list[dict] = []
    for text, confidence, bbox in annotations:
        # ocrmac bbox is normalized; convert to pixel (x1, y1, x2, y2).
        x1, y1, x2, y2 = ocrmac.convert_coordinates_pil(bbox, w, h)
        px = [
            int(round(x1)),
            int(round(y1)),
            int(round(x2 - x1)),
            int(round(y2 - y1)),
        ]
        words.append({"text": text, "confidence": float(confidence), "bbox": px})
    return words


def ocr_lines(pil_image: Image.Image) -> list[dict]:
    """Line-level Vision OCR → list of {text, confidence, bbox[x,y,w,h]}.

    The LiveText token path (`ocr_page`) is the spine of the word-box / mask
    intersection, but its per-token confidence is pinned at 1.00 — useless as a
    quality signal. Vision's *line*-level recognition is where the real
    confidence lives (Phase 0 §5: mostly 1.00 with rare ~0.50 outliers), so this
    second pass drives the quality gate's conf_ratio and the cockpit's
    per-passage low-confidence flag.
    """
    w, h = pil_image.size
    annotations = ocrmac.OCR(
        pil_image, framework="vision", recognition_level="accurate"
    ).recognize()

    lines: list[dict] = []
    for text, confidence, bbox in annotations:
        x1, y1, x2, y2 = ocrmac.convert_coordinates_pil(bbox, w, h)
        px = [
            int(round(x1)),
            int(round(y1)),
            int(round(x2 - x1)),
            int(round(y2 - y1)),
        ]
        lines.append({"text": text, "confidence": float(confidence), "bbox": px})
    return lines
