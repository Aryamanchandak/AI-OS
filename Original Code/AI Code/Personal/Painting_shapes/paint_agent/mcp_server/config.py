import pyautogui

SCREEN_RESOLUTION = (2560, 1600)   # run pyautogui.size() to verify

# Default canvas corners expressed in Keynote slide coordinates (points).
# Keynote default slide is 1920 × 1080. Override via set_canvas_corners at runtime.
CANVAS_CORNERS = {
    "top_left":     (160,  90),
    "top_right":    (1760, 90),
    "bottom_left":  (160,  990),
    "bottom_right": (1760, 990),
}

# Keynote slide dimensions in points
KEYNOTE_SLIDE = {"width": 1920, "height": 1080}

# Screen pixel position of Keynote's toolbar "Shape" button.
# Calibrate: run tests/find_coords.py while Keynote is open, hover over the
# shapes icon in the toolbar (overlapping-shapes icon, usually 4th–6th button).
KEYNOTE_TOOLBAR = {
    "shape_button": (933, 67),   # ← calibrate with find_coords.py
}

# Screen pixel position of the OVAL in Keynote's shape picker panel.
# The picker appears below the toolbar after clicking the shape button.
# Oval is the 3rd shape in the first row of the picker.
# Calibrate: click the shape button, then run find_coords.py while picker is visible.
KEYNOTE_SHAPE_PICKER = {
    "oval": (1101, 228),          # ← calibrate with find_coords.py
}

APP_LOAD_WAIT    = 3.0   # seconds after opening Keynote
TOOL_SELECT_WAIT = 0.4   # seconds after clicking a toolbar button
ACTION_WAIT      = 0.2   # general pause between actions

DRAWING_APP = "keynote"
