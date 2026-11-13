"""Screen capture and set-of-marks annotation — the OS analogue of
browser/highlight.py.

The Retina problem is the whole reason this file is careful. `screencapture`
returns a buffer in *pixels* (2x on Retina), while AX geometry and CGEvent
clicks are in *points* (1x). Annotating a 2x image with 1x boxes draws every
box in the top-left quadrant, and the model then reports marks that click
nowhere near the control. So: we detect the scale from the captured image,
draw in pixel space, and downscale the delivered image — but every
coordinate handed back to the dispatcher stays in points. Points in, points
out; pixels exist only inside this module.
"""
from __future__ import annotations

import base64
import io
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

import Quartz

from .ax import Element


# Cycled so adjacent boxes are distinguishable; high-contrast on both light
# and dark UIs.
_COLORS = ["#FF3B30", "#007AFF", "#34C759", "#FF9500", "#AF52DE", "#00C7BE"]


def screen_size() -> tuple[int, int]:
    """Main display size in points."""
    d = Quartz.CGMainDisplayID()
    return int(Quartz.CGDisplayPixelsWide(d)), int(Quartz.CGDisplayPixelsHigh(d))


def capture(path: str | None = None) -> tuple[bytes, float]:
    """Capture the main display. Returns (png_bytes, scale) where `scale` is
    pixels-per-point (2.0 on Retina).

    `-x` suppresses the shutter sound, `-C` omits the cursor — a captured
    cursor becomes a distractor the model sometimes mistakes for a UI mark.
    """
    tmp = path or str(Path(tempfile.mkdtemp()) / "screen.png")
    subprocess.run(["/usr/sbin/screencapture", "-x", "-C", tmp],
                   capture_output=True, timeout=30)
    # Without Screen Recording permission `screencapture` exits quietly and
    # writes no file at all. Left alone that surfaces as a FileNotFoundError
    # three frames up, which reads like a bug in the driver rather than a
    # missing grant — so name it here, at the point of truth.
    if not Path(tmp).exists():
        raise PermissionError(
            "screencapture produced no file — Screen Recording permission is "
            "not granted to this process. Grant it in System Settings > "
            "Privacy & Security > Screen Recording, then restart the "
            "terminal app."
        )
    data = Path(tmp).read_bytes()
    pts_w, _ = screen_size()
    with Image.open(io.BytesIO(data)) as im:
        px_w = im.width
    scale = (px_w / pts_w) if pts_w else 1.0
    return data, scale


def annotate(png: bytes, elements: list[Element], scale: float,
             *, max_width: int = 1400) -> bytes:
    """Draw numbered boxes over `elements` and return the annotated PNG.

    `elements` carry point coordinates; `scale` converts them to the image's
    pixel space. The final downscale to `max_width` keeps the vision payload
    affordable without moving any mark relative to the UI beneath it."""
    im = Image.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(im)

    for i, el in enumerate(elements):
        color = _COLORS[i % len(_COLORS)]
        x, y = int(el.x * scale), int(el.y * scale)
        w, h = int(el.w * scale), int(el.h * scale)
        draw.rectangle([x, y, x + w, y + h], outline=color, width=3)
        # Label sits above the box, or inside it when the box is flush with
        # the top of the screen and there is no room above.
        label = str(el.id)
        tw, th = 9 * len(label) + 8, 20
        ly = y - th if y - th >= 0 else y
        draw.rectangle([x, ly, x + tw, ly + th], fill=color)
        draw.text((x + 4, ly + 3), label, fill="#FFFFFF")

    if im.width > max_width:
        ratio = max_width / im.width
        im = im.resize((max_width, int(im.height * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def to_data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()
