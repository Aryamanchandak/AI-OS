"""Stage 1 — headless processor.

  python process.py --inbox data/inbox --batch "Atomic Habits" --author "James Clear"

Per image (wrapped in try/except so one bad file never kills the batch):
  load(+EXIF) → file_hash dedup → OCR page → yellow mask → intersect words
  → group into passages → store. All pages land as status='new'.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from core import detect, images, ocr, quality, store

# ── Tuning knobs (validated in Phase 0 / tuned against IMG_7754) ─────────────
# Highlighter ink drifts *below* the glyphs, so pad the word box downward to
# reach the yellow beneath the text; small upward pad for the rare drift up.
WORD_PAD_DOWN_FRAC = 0.35
WORD_PAD_UP_FRAC = 0.10
KEEP_OVERLAP_FRAC = 0.10          # keep word if >=10% of its (padded) box is yellow

# Passage grouping: a new passage starts when the vertical-centre gap to the
# previous kept word exceeds this many median line-heights.
PASSAGE_GAP_LINEHEIGHTS = 1.5

# Poke-up attribution (diagnosed against IMG_7749/IMG_7754 golden failures):
# a word on the line directly ABOVE a solid highlight catches that stroke's top
# edge in its down-pad and sneaks past KEEP_OVERLAP_FRAC with zero yellow at
# glyph height. If a word has no body yellow of its own (< BODY_FAINT_FRAC) and
# a solidly-inked word (body >= BODY_SOLID_FRAC) sits directly below it, the
# overlap is attributed to that lower line and the word is dropped. Measured
# separation: leaked words score body 0.00–0.03; genuinely highlighted words
# score body >= 0.14 even at their weakest (IMG_7754 'wants') — 0.08 splits the
# gap with margin on both sides.
BODY_SOLID_FRAC = 0.30
BODY_FAINT_FRAC = 0.08
BELOW_REACH_FRAC = 1.3     # how many glyph-heights below to look for the solid line

# Phase 1 noise floor (Phase 0 findings §4): drop facing-page bleed.
#   EDGE_MARGIN_FRAC — drop a word whose box horizontal centre falls in the
#     outer N of the image width (the facing page bleeds into a side edge).
#   MIN_PASSAGE_WORDS — drop passages shorter than this after grouping.
EDGE_MARGIN_FRAC = 0.06
MIN_PASSAGE_WORDS = 2

# Confidence floor for the quality signal. Vision *line* confidence bottoms out
# AT 0.50 (never below — Phase 0 §5), so the gate/cockpit use <= this value, not
# the spec-literal "< 0.5", or the feature is dead code on real photos.
LOW_CONF = 0.5

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".bmp"}


def _padded_box(bbox: list[int]) -> tuple[int, int, int, int]:
    """OCR [x,y,w,h] → padded (x1,y1,x2,y2). Pad biased downward to the ink."""
    x, y, w, h = bbox
    y1 = y - h * WORD_PAD_UP_FRAC
    y2 = y + h + h * WORD_PAD_DOWN_FRAC
    return int(round(x)), int(round(y1)), int(round(x + w)), int(round(y2))


def _overlap_fraction(mask: np.ndarray, box: tuple[int, int, int, int]) -> float:
    h, w = mask.shape
    x1 = max(0, box[0]); y1 = max(0, box[1])
    x2 = min(w, box[2]); y2 = min(h, box[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    sub = mask[y1:y2, x1:x2]
    if sub.size == 0:
        return 0.0
    return float(np.count_nonzero(sub)) / float(sub.size)


def _keep_words(words: list[dict], mask: np.ndarray, img_w: int) -> list[dict]:
    """Keep words overlapping yellow, dropping edge bleed and poke-up leaks."""
    left_edge = img_w * EDGE_MARGIN_FRAC
    right_edge = img_w * (1.0 - EDGE_MARGIN_FRAC)
    kept = []
    for word in words:
        x, y, w, h = word["bbox"]
        cx = x + w / 2.0
        if cx < left_edge or cx > right_edge:        # facing-page edge bleed
            continue
        box = _padded_box(word["bbox"])
        if _overlap_fraction(mask, box) >= KEEP_OVERLAP_FRAC:
            word = dict(word)
            word["_body"] = _overlap_fraction(mask, (x, y, x + w, y + h))
            # Centre + height from the *padded* box. The down-bias pad inflates
            # height to ~1.45x the glyph box, which (validated in Phase 0) is
            # what makes the gap threshold bridge generous line-leading while
            # still splitting on genuine block jumps.
            word["_cy"] = (box[1] + box[3]) / 2.0
            word["_ph"] = box[3] - box[1]
            kept.append(word)

    solid = [w for w in kept if w["_body"] >= BODY_SOLID_FRAC]

    def _poke_up_leak(word: dict) -> bool:
        """Word with no glyph-level yellow whose pad yellow is the top edge of a
        solid highlight on the line below — attribute and drop."""
        if word["_body"] >= BODY_FAINT_FRAC:
            return False
        x, y, w, h = word["bbox"]
        for s in solid:
            sx, sy, sw, sh = s["bbox"]
            if not (y + 0.5 * h < sy <= y + h * (1.0 + BELOW_REACH_FRAC)):
                continue                              # not the line directly below
            if sx < x + w and x < sx + sw:            # horizontal overlap
                return True
        return False

    return [w for w in kept if not _poke_up_leak(w)]


def _group_passages(kept: list[dict]) -> list[list[dict]]:
    """Walk kept words in reading order; split on a large vertical-centre gap."""
    if not kept:
        return []
    heights = [w["_ph"] for w in kept]
    line_height = float(np.median(heights))
    threshold = PASSAGE_GAP_LINEHEIGHTS * max(line_height, 1.0)
    passages: list[list[dict]] = [[kept[0]]]
    for prev, cur in zip(kept, kept[1:]):
        if abs(cur["_cy"] - prev["_cy"]) > threshold:
            passages.append([cur])
        else:
            passages[-1].append(cur)
    return passages


def _passage_text(words: list[dict]) -> str:
    """Join words; de-hyphenate line-break hyphens (under-\\nstand → understand)."""
    out = ""
    for i, wd in enumerate(words):
        t = wd["text"]
        if i == 0:
            out = t
        elif out.endswith("-"):
            out = out[:-1] + t
        else:
            out += " " + t
    return out


def _union_bbox(words: list[dict]) -> list[int]:
    xs1 = [w["bbox"][0] for w in words]
    ys1 = [w["bbox"][1] for w in words]
    xs2 = [w["bbox"][0] + w["bbox"][2] for w in words]
    ys2 = [w["bbox"][1] + w["bbox"][3] for w in words]
    x1, y1 = min(xs1), min(ys1)
    return [x1, y1, max(xs2) - x1, max(ys2) - y1]


def _boxes_overlap(a: list[int], b: list[int]) -> bool:
    """True if two [x,y,w,h] rectangles intersect."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _passage_min_conf(union: list[int], lines: list[dict], word_min: float) -> float:
    """Lowest Vision *line* confidence overlapping the passage's union bbox.

    LiveText word tokens are pinned at 1.00, so the cockpit's low-confidence flag
    can only fire if min_conf is re-sourced from the line-level pass. Falls back
    to the word-token min when no line overlaps (keeps a sane value, never None).
    """
    overlapping = [ln["confidence"] for ln in lines if _boxes_overlap(union, ln["bbox"])]
    return min(overlapping) if overlapping else word_min


def process_image(path: Path, args) -> tuple[int, int, bool]:
    """Process one image → (n_passages_stored, inserted, flagged_retake).

    inserted is 1 if a new page row was written, 0 on a dedup skip. flagged_retake
    is True when the quality gate bounced this page. Raises on error.
    """
    hash_ = images.file_hash(path)
    pil = images.load_image(path)
    rgb = np.asarray(pil)
    img_w = pil.size[0]

    # Quality scores (spec §6). Computed on the same downscaled array the rest of
    # the pipeline uses; conf_ratio comes from the line-level Vision pass.
    blur = quality.blur_score(rgb)
    glare = quality.glare_score(rgb)
    lines = ocr.ocr_lines(pil)
    conf_ratio = (
        sum(1 for ln in lines if ln["confidence"] <= LOW_CONF) / len(lines)
        if lines else 0.0
    )
    flagged = quality.quality_gate(blur, glare, conf_ratio)
    status = "retake" if flagged else "new"

    words = ocr.ocr_page(pil)
    mask = detect.yellow_mask(rgb, args.hsv)
    kept = _keep_words(words, mask, img_w)
    groups = _group_passages(kept)
    groups = [g for g in groups if len(g) >= MIN_PASSAGE_WORDS]

    page_id = store.insert_page(
        args.db,
        batch=args.batch,
        author=args.author,
        image_path=str(path),
        file_hash=hash_,
        status=status,
        blur_score=blur,
        glare_score=glare,
        conf_ratio=conf_ratio,
        book_meta=getattr(args, "book_meta", None),
    )
    if page_id is None:
        return (0, 0, False)        # already processed (dedup) — skip whole image

    # Raw recognizer text per passage. With --clean, an optional text-only LLM
    # pass (core/cleanup) corrects obvious OCR garbles into edited_text while the
    # raw string stays in ocr_text. Off by default → edited == raw (byte-identical
    # to the un-cleaned path). Guarded so a gateway hiccup never kills the batch.
    raw_texts = [_passage_text(g) for g in groups]
    if getattr(args, "clean", False) and raw_texts:
        from core import cleanup
        edited_texts = cleanup.clean_passages(raw_texts)
    else:
        edited_texts = raw_texts

    for g, raw, edited in zip(groups, raw_texts, edited_texts):
        union = _union_bbox(g)
        word_min = min(w["confidence"] for w in g)
        store.insert_passage(
            args.db,
            page_id,
            bbox=union,
            ocr_text=raw,
            edited_text=edited,
            min_conf=_passage_min_conf(union, lines, word_min),
        )
    return (len(groups), 1, flagged)


def main() -> int:
    ap = argparse.ArgumentParser(description="Highlight Grabber — processor")
    ap.add_argument("--inbox", required=True)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--author", default=None)
    ap.add_argument("--db", default="data/processed.db")
    ap.add_argument("--hsv", default=None,
                    help='lower HSV floor "H,S,V" e.g. "25,100,130"')
    ap.add_argument("--clean", action="store_true",
                    help="pre-fill edited_text with an LLM OCR-cleanup pass "
                         "(needs the AI Code LLM gateway running on :8107; raw "
                         "OCR is always preserved in ocr_text)")
    args = ap.parse_args()

    if args.hsv:
        args.hsv = tuple(int(x) for x in args.hsv.split(","))

    store.init_db(args.db)
    inbox = Path(args.inbox)
    paths = sorted(p for p in inbox.iterdir() if p.suffix.lower() in IMAGE_EXTS)

    inserted = skipped = passages_total = 0
    errored: list[str] = []          # threw an exception (per-image isolation)
    gated: list[str] = []            # processed fine but failed the quality gate

    for path in paths:
        try:
            n_passages, did_insert, flagged = process_image(path, args)
            if did_insert:
                inserted += 1
                passages_total += n_passages
                tag = "RETAKE" if flagged else "OK"
                print(f"  {tag:<6} {path.name:<28} {n_passages} passages")
                if flagged:
                    gated.append(path.name)
            else:
                skipped += 1
                print(f"  skip {path.name:<28} (already processed)")
        except Exception as e:        # per-image isolation
            errored.append(path.name)
            print(f"  !!   {path.name:<28} {type(e).__name__}: {e}")

    retake = gated + errored
    print("-" * 60)
    print(f"images: {len(paths)}  inserted: {inserted}  skipped(dedup): {skipped}  "
          f"gated(retake): {len(gated)}  errored: {len(errored)}")
    print(f"passages stored this run: {passages_total}")
    if retake:
        print("RETAKE LIST (reshoot and re-run):")
        for name in gated:
            print(f"  - {name}  (failed quality gate)")
        for name in errored:
            print(f"  - {name}  (errored while processing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
