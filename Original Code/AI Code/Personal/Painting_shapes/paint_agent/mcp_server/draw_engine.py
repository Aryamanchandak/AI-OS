"""
Keynote drawing engine.

Shapes and text are created via AppleScript (osascript) which gives exact
slide-coordinate control. The oval/circle is the only exception: Keynote's
AppleScript dictionary only supports rectangle shapes natively, so we use
pyautogui to click Insert → Shape picker → oval, then reposition via script.

Coordinate system: Keynote slide points (origin = top-left of slide).
The values passed in from server.py come from geometry.py and are in the
same coordinate space the user specified in set_canvas_corners.
"""

import subprocess
import time
import pyautogui

from . import config

pyautogui.FAILSAFE = True


# ---------------------------------------------------------------------------
# AppleScript helper
# ---------------------------------------------------------------------------

def _run(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript error: {result.stderr.strip()}")
    return result.stdout.strip()


def _pause(t: float = None):
    time.sleep(t if t is not None else config.ACTION_WAIT)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

def open_drawing_app(app_name: str = None) -> str:
    w = config.KEYNOTE_SLIDE["width"]
    h = config.KEYNOTE_SLIDE["height"]
    _run(f'''
    tell application "Keynote"
        activate
        make new document with properties {{width:{w}, height:{h}}}
    end tell
    ''')
    time.sleep(config.APP_LOAD_WAIT)
    return f"Keynote launched with a blank {w}×{h} slide."


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

def draw_rectangle_on_screen(top_left: tuple, bottom_right: tuple) -> str:
    x, y = top_left
    w = bottom_right[0] - top_left[0]
    h = bottom_right[1] - top_left[1]
    _run(f'''
    tell application "Keynote"
        tell front document
            tell first slide
                set s to make new shape with properties {{position:{{{x}, {y}}}, width:{w}, height:{h}}}
                set fill of s to no fill
            end tell
        end tell
    end tell
    ''')
    return f"Rectangle drawn: {top_left} → {bottom_right}"


def draw_square_on_screen(top_left: tuple, bottom_right: tuple) -> str:
    # A square is just a rectangle with equal sides — same AppleScript path.
    x, y = top_left
    side = bottom_right[0] - top_left[0]
    _run(f'''
    tell application "Keynote"
        tell front document
            tell first slide
                set s to make new shape with properties {{position:{{{x}, {y}}}, width:{side}, height:{side}}}
                set fill of s to no fill
            end tell
        end tell
    end tell
    ''')
    return f"Square drawn: {top_left} → {bottom_right}"


def draw_circle_on_screen(center: tuple, radius: int) -> str:
    """
    Keynote's AppleScript can only make rectangles via `make new shape`.
    We use pyautogui to click the toolbar Shape button, then click the oval
    in the picker, then reposition and resize via AppleScript.

    Requires KEYNOTE_TOOLBAR["shape_button"] and KEYNOTE_SHAPE_PICKER["oval"]
    to be calibrated in config.py.
    """
    # Bring Keynote to front
    _run('tell application "Keynote" to activate')
    _pause(0.3)

    # Click the Shape toolbar button
    pyautogui.click(*config.KEYNOTE_TOOLBAR["shape_button"])
    _pause(config.TOOL_SELECT_WAIT)

    # Click the oval in the shape picker panel
    pyautogui.click(*config.KEYNOTE_SHAPE_PICKER["oval"])
    _pause(config.TOOL_SELECT_WAIT)

    # The oval is now inserted at the slide centre — reposition and resize via AppleScript
    cx, cy = center
    x = cx - radius
    y = cy - radius
    diam = radius * 2
    _run(f'''
    tell application "Keynote"
        tell front document
            tell first slide
                set s to last shape
                set position of s to {{{x}, {y}}}
                set width of s to {diam}
                set height of s to {diam}
                set fill of s to no fill
            end tell
        end tell
    end tell
    ''')
    return f"Circle drawn: center={center} radius={radius}"


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def add_text_on_screen(
    position: tuple,
    text: str,
    font_name: str,
    font_size: int,
    shape_bounds: dict,
) -> str:
    """
    Inserts a text box at `position` inside the slide.
    Width is taken from shape_bounds so the text stays inside the shape.
    Font name and size are applied via AppleScript rich text properties.
    """
    x, y = position

    # Use shape width as text box width; fall back to a sensible default
    tb_width  = shape_bounds.get("width", 400) - 40   # 20 px inset each side
    tb_height = shape_bounds.get("height", 100)

    # Guard against text overflowing the box width
    if "width" in shape_bounds:
        max_chars = shape_bounds["width"] // max(font_size // 2, 1)
        if len(text) > max_chars:
            text = text[:max_chars]

    # Escape for AppleScript string literals
    safe_text = text.replace('"', '\\"')
    safe_font = font_name.replace('"', '\\"')

    _run(f'''
    tell application "Keynote"
        tell front document
            tell first slide
                set tb to make new text item with properties {{position:{{{x}, {y}}}, width:{tb_width}, height:{tb_height}, object text:"{safe_text}"}}
                tell object text of tb
                    set font of every character to "{safe_font}"
                    set size of every character to {font_size}
                end tell
            end tell
        end tell
    end tell
    ''')
    return f"Text '{text}' placed at {position} in {font_name} {font_size}pt"
