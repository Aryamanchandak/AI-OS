"""Yellow-highlight detection via HSV color thresholding (OpenCV).

Phase 0 confirmed a single yellow ink solidly in H∈[20,35] (OpenCV scale,
H∈[0,179]). Mask false-positives are sticky tabs / glare in the margins; they
carry no text, so the word-box intersection drops them.
"""

from __future__ import annotations

import cv2
import numpy as np

# HSV lower/upper bounds (OpenCV scale: H∈[0,179], S/V∈[0,255]).
DEFAULT_LOWER = (20, 80, 120)   # H, S, V floor
DEFAULT_UPPER = (35, 255, 255)
MASK_CLOSE_KERNEL = 7           # morphological close to solidify highlighter strokes


def yellow_mask(image_rgb: np.ndarray, hsv_params: tuple | None = None) -> np.ndarray:
    """Binary yellow mask from an RGB array.

    hsv_params overrides the lower (H, S, V) floor — used by the per-batch CLI
    `--hsv` knob when lighting shifts the hue. The upper bound is held at
    DEFAULT_UPPER.
    """
    lower = np.array(hsv_params if hsv_params else DEFAULT_LOWER)
    upper = np.array(DEFAULT_UPPER)

    hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = np.ones((MASK_CLOSE_KERNEL, MASK_CLOSE_KERNEL), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask
