"""EXIF-corrected image loading and stable file hashing."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener


register_heif_opener()

MAX_LONG_EDGE = 3600


def load_image(path: str | Path) -> Image.Image:
    """Open a supported page image, apply EXIF orientation, and return RGB."""

    with Image.open(path) as source:
        transposed = ImageOps.exif_transpose(source)
        image = transposed.convert("RGB")

    long_edge = max(image.size)
    if long_edge > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / long_edge
        new_size = (round(image.width * scale), round(image.height * scale))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    return image


def file_hash(path: str | Path) -> str:
    """Return the SHA-256 hash of the original file bytes."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
