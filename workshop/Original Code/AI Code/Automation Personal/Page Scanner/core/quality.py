"""Quality gate (spec §6): cheap per-image checks that bounce bad captures to a
retake list before they cost review time.

THRESHOLDS ARE PLACEHOLDERS. They were measured against the *downscaled*
(≤2500px long-edge) working image — the same array the rest of the pipeline runs
on, NOT the full-res original — and they MUST be tuned once a genuinely bad photo
exists to calibrate against. Phase 0 had no degraded sample, so on the current
"good" inbox the real distributions are:
  blur  : 250–533   (a soft/blurry shot drops far below this; default 80 only
                     catches *severe* blur and leaves an 80–250 dead zone)
  glare : ≤0.006    (lamp hotspots push this up; default 0.04 is a guess)
  conf  : Vision line confidence is pinned at 1.00 or a discrete 0.50, never
                     *below* 0.5 — so conf_ratio uses <= 0.5 (see process.py),
                     and is effectively 0 until a capture is bad enough to make
                     Vision emit genuinely low-confidence lines.
Re-tune all three against the first real retake sample.
"""

from __future__ import annotations

import cv2
import numpy as np

# Starting defaults — TUNE per real photos (see module docstring).
BLUR_MIN = 80.0          # blur < BLUR_MIN  → retake (low Laplacian variance = soft)
GLARE_MAX = 0.04         # glare > GLARE_MAX → retake (blown-out blob fraction)
CONF_RATIO_MAX = 0.3     # conf_ratio > CONF_RATIO_MAX → retake (OCR struggling)

GLARE_V_FLOOR = 245      # HSV V above this counts as near-white / blown out
GLARE_MIN_BLOB = 500     # only blobs larger than this (px) count as glare, not speckle


def blur_score(image_rgb: np.ndarray) -> float:
    """Variance of the Laplacian — low = soft/blurry, high = sharp."""
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def glare_score(image_rgb: np.ndarray) -> float:
    """Fraction of the image covered by clustered blown-out (near-white) blobs.

    A lamp hotspot on glossy paper clips to pure white and eats the text under
    it. Isolated bright speckle is ignored (blobs must exceed GLARE_MIN_BLOB);
    only sizeable clusters count.
    """
    hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)
    bright = (hsv[:, :, 2] > GLARE_V_FLOOR).astype(np.uint8)
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(bright, connectivity=8)
    glare_px = sum(
        int(stats[i, cv2.CC_STAT_AREA])
        for i in range(1, n)                      # 0 is the background component
        if stats[i, cv2.CC_STAT_AREA] > GLARE_MIN_BLOB
    )
    total = image_rgb.shape[0] * image_rgb.shape[1]
    return glare_px / float(total) if total else 0.0


def quality_gate(blur: float, glare: float, conf_ratio: float) -> bool:
    """True ⇒ flag this page for retake. Any single hard failure bounces it."""
    return blur < BLUR_MIN or glare > GLARE_MAX or conf_ratio > CONF_RATIO_MAX
