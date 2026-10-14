# Agent guide: Integration-style tests that synthesize poor captures to verify quality gates and confidence flagging.
"""Phase 2 plumbing proofs — independent of whether an organic bad photo exists.

The clean inbox can't exercise the quality gate or the low-confidence flag (every
page scores blur 250–533, glare ≤0.006, and the rare 0.50 Vision lines don't fall
inside a highlighted region — Phase 0 §3/§5). These tests therefore degrade real
images on purpose to prove each path *fires* when fed genuinely bad input.

  .venv/bin/python tests/test_phase2.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import images, ocr, quality  # noqa: E402
import process as P                    # noqa: E402

INBOX = ROOT / "data" / "inbox"


def test_blur_gate_fires_on_blurred_image() -> None:
    """A sharp page passes; the same page heavily blurred trips the blur gate."""
    rgb = np.asarray(images.load_image(INBOX / "IMG_7748.JPG"))
    sharp = quality.blur_score(rgb)
    assert sharp >= quality.BLUR_MIN, f"sharp image should pass gate, got {sharp:.1f}"
    assert quality.quality_gate(sharp, 0.0, 0.0) is False

    blurred = cv2.GaussianBlur(rgb, (0, 0), sigmaX=6)
    soft = quality.blur_score(blurred)
    assert soft < quality.BLUR_MIN, f"blurred image should fail gate, got {soft:.1f}"
    assert quality.quality_gate(soft, 0.0, 0.0) is True
    print(f"  blur gate: sharp={sharp:.1f} (pass) → blurred={soft:.1f} (RETAKE)  ✓")


def test_glare_gate_fires_on_synthetic_hotspot() -> None:
    """Painting a large blown-out blob pushes glare_score past the threshold."""
    rgb = np.asarray(images.load_image(INBOX / "IMG_7748.JPG")).copy()
    base = quality.glare_score(rgb)
    h, w = rgb.shape[:2]
    cv2.circle(rgb, (w // 2, h // 2), int(min(h, w) * 0.22), (255, 255, 255), -1)
    hot = quality.glare_score(rgb)
    assert base <= quality.GLARE_MAX < hot, f"base={base:.4f} hot={hot:.4f}"
    assert quality.quality_gate(500.0, hot, 0.0) is True
    print(f"  glare gate: base={base:.4f} (pass) → hotspot={hot:.4f} (RETAKE)  ✓")


def test_passage_min_conf_picks_up_low_line() -> None:
    """The cockpit low-confidence path: a passage union that overlaps a sub-0.5
    Vision line must report min_conf <= 0.5 (word tokens alone are pinned at 1.0)."""
    pil = images.load_image(INBOX / "IMG_7754.JPG")
    lines = ocr.ocr_lines(pil)
    low = [ln for ln in lines if ln["confidence"] <= P.LOW_CONF]
    assert low, "expected at least one ≤0.5 Vision line on IMG_7754 (Phase 0 §5)"
    # A passage union box that exactly covers the first low-confidence line.
    union = low[0]["bbox"]
    mc = P._passage_min_conf(union, lines, word_min=1.0)
    assert mc <= P.LOW_CONF, f"min_conf should reflect the low line, got {mc}"
    # And a passage far away (1px box in the corner) falls back to the word min.
    far = P._passage_min_conf([0, 0, 1, 1], lines, word_min=1.0)
    assert far == 1.0
    print(f"  min_conf re-source: overlapping low line → {mc} (flags); "
          f"non-overlapping → {far} (clean)  ✓")


def test_conf_ratio_threshold_inclusive() -> None:
    """conf_ratio counts lines <= 0.5 (line conf bottoms AT 0.5; strict < is dead)."""
    pil = images.load_image(INBOX / "IMG_7754.JPG")
    lines = ocr.ocr_lines(pil)
    inclusive = sum(1 for ln in lines if ln["confidence"] <= 0.5)
    strict = sum(1 for ln in lines if ln["confidence"] < 0.5)
    assert inclusive > 0 and strict == 0, (
        f"<=0.5 should catch the 0.50 outliers ({inclusive}); <0.5 misses them ({strict})")
    print(f"  conf_ratio threshold: <=0.5 catches {inclusive} line(s), "
          f"<0.5 catches {strict} (would be dead code)  ✓")


if __name__ == "__main__":
    print("Phase 2 plumbing proofs:")
    test_blur_gate_fires_on_blurred_image()
    test_glare_gate_fires_on_synthetic_hotspot()
    test_passage_min_conf_picks_up_low_line()
    test_conf_ratio_threshold_inclusive()
    print("\nall passed ✓")
