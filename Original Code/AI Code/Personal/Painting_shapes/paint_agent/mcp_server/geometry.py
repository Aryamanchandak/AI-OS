def compute_center(corners: dict) -> tuple[int, int]:
    """
    corners: {"top_left": (x,y), "top_right": (x,y), "bottom_left": (x,y), "bottom_right": (x,y)}
    Returns mean of all 4 corner coordinates as integer (cx, cy).
    """
    xs = [corners["top_left"][0], corners["top_right"][0],
          corners["bottom_left"][0], corners["bottom_right"][0]]
    ys = [corners["top_left"][1], corners["top_right"][1],
          corners["bottom_left"][1], corners["bottom_right"][1]]
    return (int(sum(xs) / 4), int(sum(ys) / 4))


def get_circle_bounds(center: tuple, radius: int) -> dict:
    cx, cy = center
    return {
        "center": (cx, cy),
        "radius": radius,
        "bbox": (cx - radius, cy - radius, cx + radius, cy + radius),
    }


def get_square_bounds(center: tuple, side: int) -> dict:
    cx, cy = center
    half = side // 2
    return {
        "top_left":     (cx - half, cy - half),
        "bottom_right": (cx + half, cy + half),
        "width":  side,
        "height": side,
    }


def get_rectangle_bounds(center: tuple, width: int, height: int) -> dict:
    cx, cy = center
    hw, hh = width // 2, height // 2
    return {
        "top_left":     (cx - hw, cy - hh),
        "bottom_right": (cx + hw, cy + hh),
        "width":  width,
        "height": height,
    }


def get_text_origin(shape_bounds: dict, inset: int = 20) -> tuple[int, int]:
    """
    Returns a safe text start point inside the shape with padding from edges.
    Works for rect/square (uses top_left) and circle (uses center shifted up-left).
    """
    if "top_left" in shape_bounds:
        tl = shape_bounds["top_left"]
        return (tl[0] + inset, tl[1] + inset)
    # circle case: shift center up and left by 40% of radius
    cx, cy = shape_bounds["center"]
    r = shape_bounds["radius"]
    offset = int(r * 0.4)
    return (cx - offset, cy - offset)
