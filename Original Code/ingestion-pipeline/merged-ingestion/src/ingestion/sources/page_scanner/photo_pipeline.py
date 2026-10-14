"""Pure photo-to-highlighted-passage extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from ingestion.sources.page_scanner import detect, images, ocr, quality
from ingestion.sources.page_scanner.detect import HsvFloor
from ingestion.sources.page_scanner.ocr import OcrItem


WORD_PAD_DOWN_FRAC = 0.35
WORD_PAD_UP_FRAC = 0.10
KEEP_OVERLAP_FRAC = 0.10
PASSAGE_GAP_LINEHEIGHTS = 1.5
BODY_SOLID_FRAC = 0.30
BODY_FAINT_FRAC = 0.08
BELOW_REACH_FRAC = 1.3
EDGE_MARGIN_FRAC = 0.06
MIN_PASSAGE_WORDS = 2
LOW_CONF = 0.5

UInt8Array = NDArray[np.uint8]
WorkingWord = dict[str, Any]


@dataclass(frozen=True)
class Passage:
    text: str
    bbox: list[int]
    min_conf: float


@dataclass(frozen=True)
class PhotoResult:
    passages: list[Passage]
    blur_score: float
    glare_score: float
    conf_ratio: float
    flagged_retake: bool
    file_hash: str


def _padded_box(bbox: list[int]) -> tuple[int, int, int, int]:
    x, y, width, height = bbox
    y1 = y - height * WORD_PAD_UP_FRAC
    y2 = y + height + height * WORD_PAD_DOWN_FRAC
    return (
        int(round(x)),
        int(round(y1)),
        int(round(x + width)),
        int(round(y2)),
    )


def _overlap_fraction(
    mask: UInt8Array, box: tuple[int, int, int, int]
) -> float:
    height, width = mask.shape
    x1, y1 = max(0, box[0]), max(0, box[1])
    x2, y2 = min(width, box[2]), min(height, box[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    sub = mask[y1:y2, x1:x2]
    if sub.size == 0:
        return 0.0
    return float(np.count_nonzero(sub)) / float(sub.size)


def _keep_words(
    words: list[OcrItem], mask: UInt8Array, image_width: int
) -> list[WorkingWord]:
    """Keep highlighted words while rejecting edge bleed and poke-up leaks."""

    left_edge = image_width * EDGE_MARGIN_FRAC
    right_edge = image_width * (1.0 - EDGE_MARGIN_FRAC)
    kept: list[WorkingWord] = []
    for item in words:
        x, y, width, height = item["bbox"]
        center_x = x + width / 2.0
        if center_x < left_edge or center_x > right_edge:
            continue
        padded = _padded_box(item["bbox"])
        if _overlap_fraction(mask, padded) >= KEEP_OVERLAP_FRAC:
            word: WorkingWord = dict(item)
            word["_body"] = _overlap_fraction(
                mask, (x, y, x + width, y + height)
            )
            word["_cy"] = (padded[1] + padded[3]) / 2.0
            word["_ph"] = padded[3] - padded[1]
            kept.append(word)

    solid = [word for word in kept if float(word["_body"]) >= BODY_SOLID_FRAC]

    def is_poke_up_leak(word: WorkingWord) -> bool:
        if float(word["_body"]) >= BODY_FAINT_FRAC:
            return False
        x, y, width, height = cast(list[int], word["bbox"])
        for solid_word in solid:
            solid_x, solid_y, solid_width, _solid_height = cast(
                list[int], solid_word["bbox"]
            )
            if not (
                y + 0.5 * height
                < solid_y
                <= y + height * (1.0 + BELOW_REACH_FRAC)
            ):
                continue
            if solid_x < x + width and x < solid_x + solid_width:
                return True
        return False

    return [word for word in kept if not is_poke_up_leak(word)]


def _group_passages(kept: list[WorkingWord]) -> list[list[WorkingWord]]:
    if not kept:
        return []
    heights = [float(word["_ph"]) for word in kept]
    line_height = float(np.median(heights))
    threshold = PASSAGE_GAP_LINEHEIGHTS * max(line_height, 1.0)
    passages: list[list[WorkingWord]] = [[kept[0]]]
    for previous, current in zip(kept, kept[1:]):
        if abs(float(current["_cy"]) - float(previous["_cy"])) > threshold:
            passages.append([current])
        else:
            passages[-1].append(current)
    return passages


def _passage_text(words: list[WorkingWord]) -> str:
    output = ""
    for index, word in enumerate(words):
        text = str(word["text"])
        if index == 0:
            output = text
        elif output.endswith("-"):
            output = output[:-1] + text
        else:
            output += " " + text
    return output


def _union_bbox(words: list[WorkingWord]) -> list[int]:
    boxes = [cast(list[int], word["bbox"]) for word in words]
    x1 = min(box[0] for box in boxes)
    y1 = min(box[1] for box in boxes)
    x2 = max(box[0] + box[2] for box in boxes)
    y2 = max(box[1] + box[3] for box in boxes)
    return [x1, y1, x2 - x1, y2 - y1]


def _boxes_overlap(left: list[int], right: list[int]) -> bool:
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    return (
        left_x < right_x + right_width
        and right_x < left_x + left_width
        and left_y < right_y + right_height
        and right_y < left_y + left_height
    )


def _passage_min_conf(
    union: list[int], lines: list[OcrItem], word_min: float
) -> float:
    overlapping = [
        line["confidence"]
        for line in lines
        if _boxes_overlap(union, line["bbox"])
    ]
    return min(overlapping) if overlapping else word_min


def _build_passages(
    kept: list[WorkingWord], lines: list[OcrItem]
) -> list[Passage]:
    groups = [
        group
        for group in _group_passages(kept)
        if len(group) >= MIN_PASSAGE_WORDS
    ]
    passages: list[Passage] = []
    for group in groups:
        union = _union_bbox(group)
        passages.append(
            Passage(
                text=_passage_text(group),
                bbox=union,
                min_conf=_passage_min_conf(
                    union,
                    lines,
                    min(float(word["confidence"]) for word in group),
                ),
            )
        )
    return passages


def process_photo(
    path: Path, *, hsv_params: HsvFloor | None = None
) -> PhotoResult:
    """OCR and group one photo without writing to a database."""

    file_digest = images.file_hash(path)
    pil_image = images.load_image(path)
    try:
        rgb = np.asarray(pil_image)
        image_width = pil_image.size[0]
        blur = quality.blur_score(rgb)
        glare = quality.glare_score(rgb)
        lines = ocr.ocr_lines(pil_image)
        conf_ratio = (
            sum(1 for line in lines if line["confidence"] <= LOW_CONF) / len(lines)
            if lines
            else 0.0
        )
        flagged_retake = quality.quality_gate(blur, glare, conf_ratio)
        words = ocr.ocr_page(pil_image)
        if not words and lines:
            words = ocr.words_from_lines(lines)
        mask = detect.yellow_mask(rgb, hsv_params)
        kept = _keep_words(words, mask, image_width)
        passages = _build_passages(kept, lines)
    finally:
        pil_image.close()

    return PhotoResult(
        passages=passages,
        blur_score=blur,
        glare_score=glare,
        conf_ratio=conf_ratio,
        flagged_retake=flagged_retake,
        file_hash=file_digest,
    )
