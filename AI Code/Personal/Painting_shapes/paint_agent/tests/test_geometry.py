import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp_server.geometry import (
    compute_center,
    get_circle_bounds,
    get_rectangle_bounds,
    get_square_bounds,
    get_text_origin,
)


def test_center():
    corners = {
        "top_left":     (0, 0),
        "top_right":    (1000, 0),
        "bottom_left":  (0, 800),
        "bottom_right": (1000, 800),
    }
    cx, cy = compute_center(corners)
    assert cx == 500
    assert cy == 400


def test_center_asymmetric():
    corners = {
        "top_left":     (100, 50),
        "top_right":    (900, 50),
        "bottom_left":  (100, 750),
        "bottom_right": (900, 750),
    }
    cx, cy = compute_center(corners)
    assert cx == 500
    assert cy == 400


def test_square_is_symmetric():
    bounds = get_square_bounds((500, 400), side=200)
    assert bounds["top_left"]     == (400, 300)
    assert bounds["bottom_right"] == (600, 500)
    assert bounds["width"]  == 200
    assert bounds["height"] == 200


def test_circle_bounds():
    bounds = get_circle_bounds((500, 400), radius=100)
    assert bounds["center"] == (500, 400)
    assert bounds["radius"] == 100
    assert bounds["bbox"]   == (400, 300, 600, 500)


def test_rectangle_bounds():
    bounds = get_rectangle_bounds((500, 400), width=400, height=150)
    assert bounds["top_left"]     == (300, 325)
    assert bounds["bottom_right"] == (700, 475)
    assert bounds["width"]  == 400
    assert bounds["height"] == 150


def test_text_inside_rectangle():
    rect = get_rectangle_bounds((500, 400), width=400, height=150)
    origin = get_text_origin(rect, inset=20)
    assert origin[0] > rect["top_left"][0]
    assert origin[1] > rect["top_left"][1]
    assert origin[0] < rect["bottom_right"][0]
    assert origin[1] < rect["bottom_right"][1]


def test_text_inside_circle():
    circle = get_circle_bounds((500, 400), radius=100)
    origin = get_text_origin(circle, inset=20)
    # origin should be within the bounding box
    assert origin[0] >= circle["bbox"][0]
    assert origin[1] >= circle["bbox"][1]
