"""Image loading: HEIC/JPEG/PNG → EXIF-corrected RGB, plus file hashing.

EXIF orientation is load-bearing: every Phase 0 sample was stored sideways
(orientation=6). Skip the transpose and pages OCR to garbage. Non-negotiable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

# HEIC is the iPhone default; register before PIL can open .heic/.heif.
register_heif_opener()

# Long-edge cap for the working image. Raised from 2500 → 3600: an iPhone photo
# is ~4032px, so 2500 threw away ~40% of linear resolution before Vision ever saw
# it — the biggest recoverable accuracy loss on small body text. Processing is
# headless (slow-is-fine), so the larger array is an acceptable trade for OCR
# fidelity. Passage-grouping math is all fractional (scale-invariant), so this
# does not move the grouping thresholds. Verified against golden/check.py.
MAX_LONG_EDGE = 3600


def load_image(path: str | Path) -> Image.Image:
    """Open (incl. HEIC), apply EXIF orientation, downscale, return RGB image."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)        # iPhone stores rotation as metadata
    img = img.convert("RGB")

    long_edge = max(img.size)
    if long_edge > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / long_edge
        new_size = (round(img.width * scale), round(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)
    return img


def file_hash(path: str | Path) -> str:
    """sha256 of the raw file bytes — the dedup key (re-running is idempotent)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
