"""Yellow-highlight detection using an HSV mask."""

from __future__ import annotations

from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray


HsvFloor = tuple[int, int, int]
UInt8Array = NDArray[np.uint8]

DEFAULT_LOWER: HsvFloor = (20, 80, 120)
DEFAULT_UPPER: HsvFloor = (35, 255, 255)
MASK_CLOSE_KERNEL = 7


def yellow_mask(
    image_rgb: UInt8Array, hsv_params: HsvFloor | None = None
) -> UInt8Array:
    """Build a binary yellow mask from an RGB image array."""

    lower = np.array(hsv_params if hsv_params else DEFAULT_LOWER)
    upper = np.array(DEFAULT_UPPER)
    hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = np.ones((MASK_CLOSE_KERNEL, MASK_CLOSE_KERNEL), np.uint8)
    return cast(
        UInt8Array, cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    )
