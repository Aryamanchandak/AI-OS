"""Cheap image-quality signals used to flag page photos for retaking."""

from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray


UInt8Array = NDArray[np.uint8]

BLUR_MIN = 80.0
GLARE_MAX = 0.04
CONF_RATIO_MAX = 0.3

GLARE_V_FLOOR = 245
GLARE_MIN_BLOB = 500


def blur_score(image_rgb: UInt8Array) -> float:
    """Variance of the Laplacian; lower values indicate blur."""

    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def glare_score(image_rgb: UInt8Array) -> float:
    """Return the fraction covered by sizeable blown-out regions."""

    hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)
    bright = (hsv[:, :, 2] > GLARE_V_FLOOR).astype(np.uint8)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        bright, connectivity=8
    )
    glare_pixels = sum(
        int(stats[index, cv2.CC_STAT_AREA])
        for index in range(1, count)
        if stats[index, cv2.CC_STAT_AREA] > GLARE_MIN_BLOB
    )
    total = image_rgb.shape[0] * image_rgb.shape[1]
    return glare_pixels / float(total) if total else 0.0


def quality_gate(blur: float, glare: float, conf_ratio: float) -> bool:
    """Return true when any one quality signal requires a retake."""

    return blur < BLUR_MIN or glare > GLARE_MAX or conf_ratio > CONF_RATIO_MAX
