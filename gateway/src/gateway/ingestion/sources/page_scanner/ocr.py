"""Apple Vision OCR through ocrmac."""

from __future__ import annotations

import re
from typing import Any, TypedDict, cast

from PIL import Image


class OcrItem(TypedDict):
    text: str
    confidence: float
    bbox: list[int]


def _ocrmac() -> Any:
    try:
        import ocrmac.ocrmac as module
    except ImportError as exc:
        raise RuntimeError(
            "Page Scanner OCR requires ocrmac and Apple Vision on macOS"
        ) from exc
    return module


def _pixel_bbox(module: Any, bbox: Any, width: int, height: int) -> list[int]:
    x1, y1, x2, y2 = cast(
        tuple[float, float, float, float],
        module.convert_coordinates_pil(bbox, width, height),
    )
    return [
        int(round(x1)),
        int(round(y1)),
        int(round(x2 - x1)),
        int(round(y2 - y1)),
    ]


def ocr_page(pil_image: Image.Image) -> list[OcrItem]:
    """Return word-level LiveText tokens in reading order."""

    module = _ocrmac()
    width, height = pil_image.size
    annotations = module.OCR(
        pil_image, framework="livetext", unit="token"
    ).recognize()
    return [
        {
            "text": str(text),
            "confidence": float(confidence),
            "bbox": _pixel_bbox(module, bbox, width, height),
        }
        for text, confidence, bbox in annotations
    ]


def ocr_lines(pil_image: Image.Image) -> list[OcrItem]:
    """Return accurate line-level Vision OCR with useful confidence values."""

    module = _ocrmac()
    width, height = pil_image.size
    annotations = module.OCR(
        pil_image, framework="vision", recognition_level="accurate"
    ).recognize()
    return [
        {
            "text": str(text),
            "confidence": float(confidence),
            "bbox": _pixel_bbox(module, bbox, width, height),
        }
        for text, confidence, bbox in annotations
    ]


def words_from_lines(lines: list[OcrItem]) -> list[OcrItem]:
    """Approximate word boxes from Vision lines when LiveText returns nothing.

    LiveText's callback/run-loop integration can silently return an empty list
    from a background worker thread.  The HTTP review service deliberately
    runs coordinator work in such a thread, while Vision line OCR remains
    reliable there.  Proportional character spans are sufficient for the
    yellow-mask overlap test and keep a transient framework limitation from
    turning a visibly highlighted page into a false retake.
    """

    words: list[OcrItem] = []
    for line in lines:
        text = line["text"]
        if not text:
            continue
        x, y, width, height = line["bbox"]
        length = len(text)
        for match in re.finditer(r"\S+", text):
            start = x + round(width * match.start() / length)
            end = x + round(width * match.end() / length)
            words.append(
                {
                    "text": match.group(),
                    "confidence": line["confidence"],
                    "bbox": [start, y, max(end - start, 1), height],
                }
            )
    return words
