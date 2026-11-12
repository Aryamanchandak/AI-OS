"""
Dry-run end-to-end test.

Simulates the full agent call sequence using real geometry + a stubbed draw engine.
No mouse is moved, no app is opened, no AppleScript runs.
Verifies coordinates are sane and tool routing in server.py works end-to-end.

Run:
    cd paint_agent
    python -m pytest tests/test_dry_run.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import unittest.mock as mock

# ---------------------------------------------------------------------------
# Stub draw_engine BEFORE server.py imports it.
# draw_engine now uses subprocess (osascript) and pyautogui — stub both so
# no real AppleScript or mouse events fire during tests.
# ---------------------------------------------------------------------------

_fake_results = {}


def _fake_open(app_name=None):
    _fake_results["open"] = "keynote"
    return "Keynote launched with a blank 1920×1080 slide. (dry-run)"


def _fake_draw_rect(tl, br):
    _fake_results["rectangle"] = (tl, br)
    return f"Rectangle drawn: {tl} → {br} (dry-run)"


def _fake_draw_square(tl, br):
    _fake_results["square"] = (tl, br)
    return f"Square drawn: {tl} → {br} (dry-run)"


def _fake_draw_circle(center, radius):
    _fake_results["circle"] = (center, radius)
    return f"Circle drawn: center={center} radius={radius} (dry-run)"


def _fake_add_text(position, text, font_name, font_size, shape_bounds):
    _fake_results["text"] = dict(
        position=position, text=text, font_name=font_name, font_size=font_size
    )
    return f"Text '{text}' at {position} in {font_name} {font_size}pt (dry-run)"


# Everything must be imported inside the with block.
# mock.patch.dict restores sys.modules on exit — any module imported inside
# that wasn't already cached gets evicted, so server.py would re-import a
# fresh draw_engine without our stubs. Keeping all imports inside avoids that.
with mock.patch.dict("sys.modules", {"pyautogui": mock.MagicMock()}):
    import mcp_server.draw_engine as de
    de.open_drawing_app         = _fake_open
    de.draw_rectangle_on_screen = _fake_draw_rect
    de.draw_square_on_screen    = _fake_draw_square
    de.draw_circle_on_screen    = _fake_draw_circle
    de.add_text_on_screen       = _fake_add_text

    import asyncio
    from mcp_server import server as srv
    from mcp_server.geometry import (
        compute_center, get_circle_bounds,
        get_square_bounds, get_rectangle_bounds, get_text_origin,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _call(name: str, **kwargs):
    result = await srv.call_tool(name, kwargs)
    return result[0].text


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _reset():
    srv._center = None
    srv._shape_bounds.clear()
    _fake_results.clear()


# Default Aim.md Phase-9 corners
_CORNERS = dict(
    top_left_x=250,  top_left_y=180,
    top_right_x=1700, top_right_y=180,
    bottom_left_x=250, bottom_left_y=950,
    bottom_right_x=1700, bottom_right_y=950,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_open_app_returns_keynote():
    _reset()
    msg = run(_call("open_drawing_app"))
    assert "Keynote" in msg or "keynote" in msg.lower()
    assert _fake_results["open"] == "keynote"


def test_center_computed_correctly():
    """Corners from Aim.md Phase 9 → center must be (975, 565)."""
    _reset()
    run(_call("open_drawing_app"))
    msg = run(_call("set_canvas_corners", **_CORNERS))
    assert "(975, 565)" in msg
    assert srv._center == (975, 565)


def test_full_sequence_coordinates():
    """Full 6-step sequence; verifies every shape's bounds and text placement."""
    _reset()
    run(_call("open_drawing_app"))
    run(_call("set_canvas_corners", **_CORNERS))

    # circle
    run(_call("draw_circle", radius=120))
    assert _fake_results["circle"] == ((975, 565), 120)
    bc = srv._shape_bounds["circle"]
    assert bc["radius"] == 120
    assert bc["bbox"]   == (855, 445, 1095, 685)

    # square
    run(_call("draw_square", side_length=250))
    bs = srv._shape_bounds["square"]
    assert bs["top_left"]     == (850, 440)
    assert bs["bottom_right"] == (1100, 690)

    # rectangle
    run(_call("draw_rectangle", width=500, height=180))
    br = srv._shape_bounds["rectangle"]
    assert br["top_left"]     == (725, 475)
    assert br["bottom_right"] == (1225, 655)

    # text inside rectangle
    run(_call("add_text", text="Centre Point", font_name="Helvetica",
              font_size=22, inside_shape="rectangle"))
    assert "Centre Point" in _fake_results["text"]["text"]
    pos = _fake_results["text"]["position"]
    assert pos[0] > br["top_left"][0]
    assert pos[1] > br["top_left"][1]
    assert pos[0] < br["bottom_right"][0]
    assert pos[1] < br["bottom_right"][1]


def test_text_inside_circle():
    _reset()
    run(_call("open_drawing_app"))
    run(_call("set_canvas_corners", **_CORNERS))
    run(_call("draw_circle", radius=100))
    msg = run(_call("add_text", text="Hello", font_name="Arial",
                    font_size=18, inside_shape="circle"))
    assert "Hello" in msg
    pos = _fake_results["text"]["position"]
    bc  = srv._shape_bounds["circle"]
    # text origin must be inside the bounding box
    assert bc["bbox"][0] <= pos[0] <= bc["bbox"][2]
    assert bc["bbox"][1] <= pos[1] <= bc["bbox"][3]


def test_text_inside_square():
    _reset()
    run(_call("open_drawing_app"))
    run(_call("set_canvas_corners", **_CORNERS))
    run(_call("draw_square", side_length=200))
    msg = run(_call("add_text", text="Square text", font_name="Georgia",
                    font_size=16, inside_shape="square"))
    assert "Square text" in msg
    pos = _fake_results["text"]["position"]
    bs  = srv._shape_bounds["square"]
    assert pos[0] > bs["top_left"][0]
    assert pos[1] > bs["top_left"][1]


def test_add_text_rejects_undrawn_shape():
    _reset()
    run(_call("open_drawing_app"))
    run(_call("set_canvas_corners", **_CORNERS))
    # circle not drawn — must get an error, not a crash
    msg = run(_call("add_text", text="Oops", font_name="Arial",
                    font_size=18, inside_shape="circle"))
    assert "Error" in msg or "not been drawn" in msg


def test_missing_center_raises():
    """Drawing before set_canvas_corners must raise ValueError."""
    _reset()
    try:
        run(_call("draw_circle", radius=50))
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "set_canvas_corners" in str(e)


def test_shapes_are_centered():
    """All shape bounds must be symmetric around the computed center."""
    _reset()
    run(_call("open_drawing_app"))
    run(_call("set_canvas_corners", **_CORNERS))
    cx, cy = srv._center

    run(_call("draw_circle", radius=80))
    bc = srv._shape_bounds["circle"]
    assert bc["center"] == (cx, cy)
    assert bc["bbox"][0] == cx - 80 and bc["bbox"][2] == cx + 80

    run(_call("draw_square", side_length=160))
    bs = srv._shape_bounds["square"]
    assert bs["top_left"][0]     == cx - 80
    assert bs["bottom_right"][0] == cx + 80

    run(_call("draw_rectangle", width=300, height=100))
    br = srv._shape_bounds["rectangle"]
    assert br["top_left"][0]     == cx - 150
    assert br["bottom_right"][0] == cx + 150


def test_multiple_text_calls_use_correct_shape():
    """Calling add_text twice for different shapes should use each shape's bounds."""
    _reset()
    run(_call("open_drawing_app"))
    run(_call("set_canvas_corners", **_CORNERS))
    run(_call("draw_square", side_length=200))
    run(_call("draw_rectangle", width=400, height=120))

    run(_call("add_text", text="In square", font_name="Arial",
              font_size=14, inside_shape="square"))
    pos_sq = _fake_results["text"]["position"]

    run(_call("add_text", text="In rect", font_name="Arial",
              font_size=14, inside_shape="rectangle"))
    pos_rect = _fake_results["text"]["position"]

    # The two origins must differ because the shapes have different bounds
    assert pos_sq != pos_rect


def test_print_all_coords():
    """Prints computed coordinates for manual inspection (always passes)."""
    _reset()
    run(_call("set_canvas_corners", **_CORNERS))
    cx, cy = srv._center

    circle = get_circle_bounds((cx, cy), 120)
    square = get_square_bounds((cx, cy), 250)
    rect   = get_rectangle_bounds((cx, cy), 500, 180)
    text_pt = get_text_origin(rect, inset=20)

    print(f"\n--- Dry-run coordinate dump (Keynote slide space) ---")
    print(f"Center      : ({cx}, {cy})")
    print(f"Circle bbox : {circle['bbox']}")
    print(f"Square      : {square['top_left']} → {square['bottom_right']}")
    print(f"Rectangle   : {rect['top_left']} → {rect['bottom_right']}")
    print(f"Text origin : {text_pt}")
    print(f"------------------------------------------------------\n")
