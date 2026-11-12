# Claude Code Implementation Plan
## Mac Screen Paint Automation via MCP + Dynamic Center-Based Drawing

---

## Context & Goal

Build an MCP server that:
1. Accepts 4 screen corner coordinates from the user
2. Computes the canvas center automatically
3. Draws a circle, square, and rectangle all centered on that point
4. Places user-specified text inside the rectangle with user-specified font and size
5. All driven by a Claude agent — no manual tool calls

Target platform: **macOS 15-inch screen**
Drawing app: **Script Editor / osascript → Keynote** (most reliable font control on Mac)
OR fallback: **pyautogui → any open app** (simpler, more portable)

Recommendation: use **pyautogui + macOS Preview or TextEdit workaround**, but the cleanest
drawing target on Mac with shape + text support is **LibreOffice Draw** (free, scriptable).

---

## Project Structure

```
paint_agent/
├── CLAUDE_CODE_PLAN.md         ← this file
├── requirements.txt
├── mcp_server/
│   ├── __init__.py
│   ├── server.py               ← MCP server: all tools live here
│   ├── geometry.py             ← pure math: center calc, shape coord calc
│   ├── draw_engine.py          ← pyautogui automation: actual drawing calls
│   └── config.py               ← screen config, app config
├── agent/
│   ├── runner.py               ← agent loop: sends prompt, handles tool calls
│   └── prompts.py              ← system prompt and user prompt templates
└── tests/
    ├── test_geometry.py        ← unit tests for all coordinate math
    └── test_dry_run.py         ← prints coords without drawing (safe test)
```

---

## Phase 1 — Environment Setup

### 1.1 Install dependencies

```
# requirements.txt
mcp
anthropic
pyautogui
Pillow          # pyautogui dependency for screenshots
```

```bash
pip install mcp anthropic pyautogui Pillow
```

On macOS, also run:
```bash
# Grant accessibility permissions to Terminal/iTerm in:
# System Preferences → Privacy & Security → Accessibility
# Without this, pyautogui cannot control the mouse
```

### 1.2 Verify pyautogui works

```python
import pyautogui
print(pyautogui.size())  # should print your screen resolution
pyautogui.moveTo(100, 100, duration=0.5)  # mouse should move
```

---

## Phase 2 — Geometry Module (Pure Math, No Automation)

### File: `mcp_server/geometry.py`

This is the clean calculation layer. No side effects, fully testable.

#### Functions to implement:

```python
def compute_center(corners: dict) -> tuple[int, int]:
    """
    Input:  corners = {
                "top_left":     (x1, y1),
                "top_right":    (x2, y2),
                "bottom_left":  (x3, y3),
                "bottom_right": (x4, y4)
            }
    Output: (center_x, center_y) as integers
    Formula: center_x = mean of all x coords, center_y = mean of all y coords
    """

def get_circle_bounds(center: tuple, radius: int) -> dict:
    """
    Returns: {
        "center": (cx, cy),
        "radius": r,
        "bbox": (cx - r, cy - r, cx + r, cy + r)   # for pyautogui arc drawing
    }
    """

def get_square_bounds(center: tuple, side: int) -> dict:
    """
    Returns: {
        "top_left":     (cx - side//2, cy - side//2),
        "bottom_right": (cx + side//2, cy + side//2),
        "width":  side,
        "height": side
    }
    """

def get_rectangle_bounds(center: tuple, width: int, height: int) -> dict:
    """
    Returns: {
        "top_left":     (cx - width//2,  cy - height//2),
        "bottom_right": (cx + width//2,  cy + height//2),
        "width":  width,
        "height": height
    }
    """

def get_text_origin(shape_bounds: dict, inset: int = 20) -> tuple[int, int]:
    """
    Returns a safe text start point inside any shape.
    For rect/square: top_left + inset on both axes
    For circle: center shifted up-left by radius * 0.4
    inset: pixel padding from shape edge
    """
```

#### Key rule: all functions are pure — input coordinates in, output coordinates out.
#### No pyautogui, no side effects, no app state.

---

## Phase 3 — Drawing Engine (Automation Layer)

### File: `mcp_server/draw_engine.py`

This layer translates coordinates into actual mouse/keyboard actions.

#### 3.1 App Launch

```python
def open_drawing_app(app_name: str = "libreoffice_draw") -> str:
    """
    Opens the target drawing app and waits for it to be ready.
    
    Supported apps:
    - "libreoffice_draw": subprocess.Popen(["soffice", "--draw"])
    - "keynote":          subprocess.Popen(["open", "-a", "Keynote"])
    - "paintbrush":       subprocess.Popen(["open", "-a", "Paintbrush"])
    
    After open: time.sleep(3) to let app load
    Returns: "App ready" or error message
    """
```

#### 3.2 Rectangle Drawing

```python
def draw_rectangle_on_screen(top_left: tuple, bottom_right: tuple) -> str:
    """
    Draws a rectangle by:
    1. Clicking the rectangle tool in the toolbar (app-specific coords)
    2. pyautogui.moveTo(*top_left)
    3. pyautogui.dragTo(*bottom_right, duration=0.8, button='left')
    
    IMPORTANT: toolbar click coords are hardcoded per app.
    These must be calibrated once per app. See config.py.
    """
```

#### 3.3 Square Drawing

```python
def draw_square_on_screen(top_left: tuple, bottom_right: tuple) -> str:
    """
    Same as rectangle but holds SHIFT while dragging to constrain to square.
    
    pyautogui.keyDown('shift')
    pyautogui.dragTo(*bottom_right, duration=0.8)
    pyautogui.keyUp('shift')
    """
```

#### 3.4 Circle Drawing

```python
def draw_circle_on_screen(center: tuple, radius: int) -> str:
    """
    Draws an ellipse/circle:
    1. Click ellipse tool in toolbar
    2. Hold SHIFT while dragging to constrain to circle
    
    Start point: (center_x - radius, center_y - radius)
    End point:   (center_x + radius, center_y + radius)
    """
```

#### 3.5 Text with Font Control

```python
def add_text_on_screen(
    position: tuple,
    text: str,
    font_name: str,
    font_size: int,
    shape_bounds: dict
) -> str:
    """
    Steps:
    1. Click text tool in toolbar
    2. Click at position inside shape
    3. Select font via menu: Format → Character → Font Name field
       OR: click font name box in toolbar, clear it, type font_name, Enter
    4. Click font size box in toolbar, clear it, type font_size, Enter
    5. pyautogui.typewrite(text, interval=0.05)
       NOTE: typewrite doesn't handle unicode — use pyperclip + Cmd+V for
             non-ASCII text
    
    Returns: confirmation string
    """
```

---

## Phase 4 — Config File

### File: `mcp_server/config.py`

This is where all hardcoded screen positions live. User edits this once.

```python
# mcp_server/config.py

SCREEN_RESOLUTION = (2560, 1600)   # 15-inch MacBook Pro retina
                                    # get via: pyautogui.size()

# The 4 corners the user defines for their usable canvas area
# These are set by the agent via set_canvas_corners tool call
# Defaults here are just placeholders
CANVAS_CORNERS = {
    "top_left":     (200,  150),
    "top_right":    (1800, 150),
    "bottom_left":  (200,  900),
    "bottom_right": (1800, 900),
}

# LibreOffice Draw toolbar button positions (calibrate these once)
# Use the coordinate finder script to get these
LIBREOFFICE_TOOLBAR = {
    "rectangle_tool": (120, 80),
    "ellipse_tool":   (145, 80),
    "text_tool":      (170, 80),
    "font_name_box":  (300, 50),
    "font_size_box":  (480, 50),
}

# Timing (increase if app is slow)
APP_LOAD_WAIT      = 3.0   # seconds after open
TOOL_SELECT_WAIT   = 0.3   # seconds after clicking a toolbar button
ACTION_WAIT        = 0.2   # seconds between actions

# Drawing app to use
DRAWING_APP = "libreoffice_draw"   # options: libreoffice_draw, keynote, paintbrush
```

---

## Phase 5 — MCP Server

### File: `mcp_server/server.py`

Exposes all tools to the agent. Tool descriptions must be verbose enough for the LLM
to call them correctly and in the right order.

#### Tools to register:

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from . import geometry, draw_engine, config

app = Server("paint-automation-server")

# Shared state — persists across tool calls within one session
_center = None
_shape_bounds = {}


@app.tool()
async def open_drawing_app() -> str:
    """
    Opens the drawing application on macOS and waits for it to be ready.
    MUST be called first before any drawing operations.
    Returns a confirmation string when the app is loaded.
    """


@app.tool()
async def set_canvas_corners(
    top_left_x: int,     top_left_y: int,
    top_right_x: int,    top_right_y: int,
    bottom_left_x: int,  bottom_left_y: int,
    bottom_right_x: int, bottom_right_y: int
) -> str:
    """
    Defines the drawable canvas area using 4 corner pixel coordinates.
    Automatically computes and stores the center point of this area.
    MUST be called before draw_circle, draw_square, or draw_rectangle.
    All subsequent shapes will be centered on the computed center point.
    Returns: the computed center coordinates as confirmation.
    """
    global _center
    corners = {
        "top_left":     (top_left_x,     top_left_y),
        "top_right":    (top_right_x,    top_right_y),
        "bottom_left":  (bottom_left_x,  bottom_left_y),
        "bottom_right": (bottom_right_x, bottom_right_y),
    }
    _center = geometry.compute_center(corners)
    return f"Canvas set. Center computed at {_center}"


@app.tool()
async def draw_circle(radius: int) -> str:
    """
    Draws a circle centered on the canvas center point.
    Args:
        radius: radius in pixels
    Requires: open_drawing_app and set_canvas_corners called first.
    Stores circle bounds for later use by add_text.
    """


@app.tool()
async def draw_square(side_length: int) -> str:
    """
    Draws a square centered on the canvas center point.
    Args:
        side_length: length of each side in pixels
    Requires: open_drawing_app and set_canvas_corners called first.
    """


@app.tool()
async def draw_rectangle(width: int, height: int) -> str:
    """
    Draws a rectangle centered on the canvas center point.
    Args:
        width:  total width in pixels
        height: total height in pixels
    Requires: open_drawing_app and set_canvas_corners called first.
    """


@app.tool()
async def add_text(
    text: str,
    font_name: str,
    font_size: int,
    inside_shape: str
) -> str:
    """
    Adds text inside one of the previously drawn shapes.
    Args:
        text:         the string to write
        font_name:    font family name e.g. "Arial", "Helvetica", "Georgia"
        font_size:    size in points e.g. 18, 24, 36
        inside_shape: which shape to write inside — "circle", "square", or "rectangle"
    Requires: the target shape must have been drawn first.
    Automatically positions text with padding from shape edges.
    Handles font selection and size via toolbar automation.
    """


if __name__ == "__main__":
    import asyncio
    asyncio.run(stdio_server(app))
```

---

## Phase 6 — Agent Runner

### File: `agent/runner.py`

```python
import anthropic
from agent.prompts import SYSTEM_PROMPT

client = anthropic.Anthropic()

def run_agent(user_instruction: str):
    """
    Sends user_instruction to Claude with MCP tools available.
    Runs the tool-use loop until stop_reason == "end_turn".
    
    Loop structure:
    1. Send message to Claude
    2. Check response for tool_use blocks
    3. For each tool_use block: call the MCP tool, get result
    4. Append tool result to message history
    5. Send updated history back to Claude
    6. Repeat until no more tool_use blocks
    """
    messages = [{"role": "user", "content": user_instruction}]
    
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,   # loaded from MCP server definitions
            messages=messages
        )
        
        if response.stop_reason == "end_turn":
            print("Agent done.")
            break
            
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = call_mcp_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
```

### File: `agent/prompts.py`

```python
SYSTEM_PROMPT = """
You are an automation agent that controls a drawing application on macOS.

You have access to tools that open an app, set a canvas area, draw shapes, and write text.

RULES — follow these strictly:
1. Always call open_drawing_app FIRST
2. Always call set_canvas_corners SECOND — use the coordinates the user provides
3. Draw shapes in any order after that
4. Call add_text LAST, only after the target shape has been drawn
5. Never skip steps. Never assume the app is already open.
6. If the user doesn't specify corners, use these Mac 15-inch defaults:
   top_left=(300, 200), top_right=(1600, 200), bottom_left=(300, 900), bottom_right=(1600, 900)
7. If the user doesn't specify a font, use Arial size 24
8. Confirm each step by reading the tool's return value before proceeding

When the user says something like:
  "draw a circle radius 100, square side 200, rectangle 400x150, write 'Hello' in Georgia 28"
You must call: open_drawing_app → set_canvas_corners → draw_circle → draw_square → draw_rectangle → add_text

Always complete all requested shapes before calling add_text.
"""
```

---

## Phase 7 — Coordinate Calibration Script

Before running anything, calibrate toolbar positions in `config.py`.

### File: `tests/find_coords.py`

```python
"""
Run this script, hover your mouse over a toolbar button in LibreOffice Draw
(or whatever app you're using), wait 3 seconds, and it prints the coordinates.
Run once per toolbar button and paste into config.py.
"""
import pyautogui, time

print("Move mouse to target position. Printing in 3 seconds...")
time.sleep(3)
x, y = pyautogui.position()
print(f"Position: ({x}, {y})")
```

---

## Phase 8 — Test Without Drawing (Dry Run)

### File: `tests/test_geometry.py`

```python
from mcp_server.geometry import compute_center, get_circle_bounds, \
    get_rectangle_bounds, get_square_bounds, get_text_origin

def test_center():
    corners = {
        "top_left": (0, 0), "top_right": (1000, 0),
        "bottom_left": (0, 800), "bottom_right": (1000, 800)
    }
    cx, cy = compute_center(corners)
    assert cx == 500
    assert cy == 400

def test_square_is_symmetric():
    bounds = get_square_bounds((500, 400), side=200)
    assert bounds["top_left"] == (400, 300)
    assert bounds["bottom_right"] == (600, 500)

def test_text_inside_rectangle():
    rect = get_rectangle_bounds((500, 400), width=400, height=150)
    origin = get_text_origin(rect, inset=20)
    # must be inside the rectangle
    assert origin[0] > rect["top_left"][0]
    assert origin[1] > rect["top_left"][1]
```

Run with: `pytest tests/test_geometry.py -v`

---

## Phase 9 — End-to-End Example

Once everything is wired up:

```bash
python -m agent.runner
```

User types:
```
My screen corners are: top_left (250, 180), top_right (1700, 180), 
bottom_left (250, 950), bottom_right (1700, 950).

Draw a circle with radius 120, a square with side 250, and a rectangle 
500 wide and 180 tall. Write "Centre Point" in Helvetica size 22 inside 
the rectangle.
```

Agent calls in order:
```
1. open_drawing_app()
2. set_canvas_corners(250, 180, 1700, 180, 250, 950, 1700, 950)
   → center computed: (975, 565)
3. draw_circle(120)
   → draws circle centered at (975, 565), radius 120
4. draw_square(250)
   → draws square: top_left=(850, 440), bottom_right=(1100, 690)
5. draw_rectangle(500, 180)
   → draws rect: top_left=(725, 475), bottom_right=(1225, 655)
6. add_text("Centre Point", "Helvetica", 22, "rectangle")
   → clicks text tool, clicks at (745, 495), sets font, types text
```

---

## Implementation Order for Claude Code

Do these in order — each phase is independently testable:

1. `mcp_server/geometry.py` → run `test_geometry.py` until all pass
2. `mcp_server/config.py` → fill in values, run `find_coords.py` to calibrate
3. `mcp_server/draw_engine.py` → test each function in isolation (open app, then draw one shape)
4. `mcp_server/server.py` → wire geometry + draw_engine into MCP tools
5. `agent/prompts.py` → write and iterate system prompt
6. `agent/runner.py` → build agent loop
7. End-to-end test with real prompt

---

## Known Risks & Mitigations

| Risk | Mitigation |
|---|---|
| pyautogui blocked by macOS permissions | Grant Accessibility access to Terminal in System Prefs |
| Toolbar coords wrong after app update | Re-run `find_coords.py`, update `config.py` |
| Text outside shape due to long string | Add character limit check in `add_text` based on shape width |
| App not loaded when first tool fires | Increase `APP_LOAD_WAIT` in config |
| SHIFT key not held for circle constraint | Use `pyautogui.keyDown/keyUp` wrapping the drag |
| Font not found in app | Fallback to "Arial" if font_name not available, log warning |
| Retina display 2x scaling | pyautogui uses logical pixels on Mac — verify with `pyautogui.size()` |