# basic imports
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.prompts import base
from mcp.types import TextContent
from mcp import types
from PIL import Image as PILImage
import math
import sys
import subprocess
import time

# instantiate an MCP server client
mcp = FastMCP("Calculator")

# Tracks whether the "paint" app (Keynote on macOS) has been opened.
paint_app = None


def _run_applescript(script: str) -> tuple[bool, str]:
    """Run an AppleScript via `osascript` and return (success, output_or_error)."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return False, result.stderr.strip() or "Unknown AppleScript error"
        return True, result.stdout.strip()
    except Exception as e:
        return False, str(e)


# =========================================================
# MATH / UTILITY TOOLS  (unchanged, already cross-platform)
# =========================================================

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    print("CALLED: add(a: int, b: int) -> int:")
    return int(a + b)

@mcp.tool()
def add_list(l: list) -> int:
    """Add all numbers in a list"""
    print("CALLED: add(l: list) -> int:")
    return sum(l)

@mcp.tool()
def subtract(a: int, b: int) -> int:
    """Subtract two numbers"""
    print("CALLED: subtract(a: int, b: int) -> int:")
    return int(a - b)

@mcp.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    print("CALLED: multiply(a: int, b: int) -> int:")
    return int(a * b)

@mcp.tool()
def divide(a: int, b: int) -> float:
    """Divide two numbers"""
    print("CALLED: divide(a: int, b: int) -> float:")
    return float(a / b)

@mcp.tool()
def power(a: int, b: int) -> int:
    """Power of two numbers"""
    print("CALLED: power(a: int, b: int) -> int:")
    return int(a ** b)

@mcp.tool()
def sqrt(a: int) -> float:
    """Square root of a number"""
    print("CALLED: sqrt(a: int) -> float:")
    return float(a ** 0.5)

@mcp.tool()
def cbrt(a: int) -> float:
    """Cube root of a number"""
    print("CALLED: cbrt(a: int) -> float:")
    return float(a ** (1 / 3))

@mcp.tool()
def factorial(a: int) -> int:
    """factorial of a number"""
    print("CALLED: factorial(a: int) -> int:")
    return int(math.factorial(a))

@mcp.tool()
def log(a: int) -> float:
    """log of a number"""
    print("CALLED: log(a: int) -> float:")
    return float(math.log(a))

@mcp.tool()
def remainder(a: int, b: int) -> int:
    """remainder of two numbers divison"""
    print("CALLED: remainder(a: int, b: int) -> int:")
    return int(a % b)

@mcp.tool()
def sin(a: int) -> float:
    """sin of a number"""
    print("CALLED: sin(a: int) -> float:")
    return float(math.sin(a))

@mcp.tool()
def cos(a: int) -> float:
    """cos of a number"""
    print("CALLED: cos(a: int) -> float:")
    return float(math.cos(a))

@mcp.tool()
def tan(a: int) -> float:
    """tan of a number"""
    print("CALLED: tan(a: int) -> float:")
    return float(math.tan(a))

@mcp.tool()
def mine(a: int, b: int) -> int:
    """special mining tool"""
    print("CALLED: mine(a: int, b: int) -> int:")
    return int(a - b - b)

@mcp.tool()
def create_thumbnail(image_path: str) -> Image:
    """Create a thumbnail from an image"""
    print("CALLED: create_thumbnail(image_path: str) -> Image:")
    img = PILImage.open(image_path)
    img.thumbnail((100, 100))
    return Image(data=img.tobytes(), format="png")

@mcp.tool()
def strings_to_chars_to_int(string: str) -> list[int]:
    """Return the ASCII values of the characters in a word"""
    print("CALLED: strings_to_chars_to_int(string: str) -> list[int]:")
    return [int(ord(char)) for char in string]

@mcp.tool()
def int_list_to_exponential_sum(int_list: list) -> float:
    """Return sum of exponentials of numbers in a list"""
    print("CALLED: int_list_to_exponential_sum(int_list: list) -> float:")
    return sum(math.exp(i) for i in int_list)

@mcp.tool()
def fibonacci_numbers(n: int) -> list:
    """Return the first n Fibonacci Numbers"""
    print("CALLED: fibonacci_numbers(n: int) -> list:")
    if n <= 0:
        return []
    fib_sequence = [0, 1]
    for _ in range(2, n):
        fib_sequence.append(fib_sequence[-1] + fib_sequence[-2])
    return fib_sequence[:n]


# =========================================================
# DRAWING TOOLS  (Mac: Keynote via AppleScript)
#
# Coordinates are in Keynote's slide coordinate space (points),
# where (0, 0) is the top-left of the slide. A standard 16:9
# slide is 1920 x 1080 points.
# =========================================================

@mcp.tool()
async def open_paint() -> dict:
    """Open Keynote (the macOS stand-in for MS Paint) with a fresh document.

    The original Windows version placed MS Paint on a secondary monitor.
    On macOS, Keynote opens on whichever display the user last used it on;
    to force a specific display, drag the window once and Keynote will
    remember the position on next launch.
    """
    global paint_app
    script = '''
    tell application "Keynote"
        activate
        make new document
    end tell
    '''
    ok, out = _run_applescript(script)
    if not ok:
        return {
            "content": [
                TextContent(type="text", text=f"Error opening Keynote: {out}")
            ]
        }
    paint_app = True
    time.sleep(0.5)
    return {
        "content": [
            TextContent(
                type="text",
                text="Keynote opened successfully with a new blank document",
            )
        ]
    }


@mcp.tool()
async def draw_rectangle(x1: int, y1: int, x2: int, y2: int) -> dict:
    """Draw a rectangle on the current Keynote slide from (x1, y1) to (x2, y2)."""
    global paint_app
    try:
        if not paint_app:
            return {
                "content": [
                    TextContent(
                        type="text",
                        text="Keynote is not open. Please call open_paint first.",
                    )
                ]
            }

        x = min(x1, x2)
        y = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)

        script = f'''
        tell application "Keynote"
            activate
            tell the front document
                tell the current slide
                    make new shape with properties {{position:{{{x}, {y}}}, width:{width}, height:{height}}}
                end tell
            end tell
        end tell
        '''
        ok, out = _run_applescript(script)
        if not ok:
            return {
                "content": [
                    TextContent(type="text", text=f"Error drawing rectangle: {out}")
                ]
            }
        return {
            "content": [
                TextContent(
                    type="text",
                    text=f"Rectangle drawn from ({x1},{y1}) to ({x2},{y2})",
                )
            ]
        }
    except Exception as e:
        return {
            "content": [
                TextContent(type="text", text=f"Error drawing rectangle: {str(e)}")
            ]
        }


@mcp.tool()
async def draw_rectangle_and_text(text: str) -> dict:
    """Draw a rectangle and add a text box with the given text in Keynote."""
    global paint_app
    try:
        if not paint_app:
            return {
                "content": [
                    TextContent(
                        type="text",
                        text="Keynote is not open. Please call open_paint first.",
                    )
                ]
            }

        # Escape characters that would break the AppleScript string literal.
        safe_text = text.replace("\\", "\\\\").replace('"', '\\"')

        script = f'''
        tell application "Keynote"
            activate
            tell the front document
                tell the current slide
                    make new shape with properties {{position:{{300, 300}}, width:500, height:200}}
                    make new text item with properties {{position:{{320, 360}}, width:460, object text:"{safe_text}"}}
                end tell
            end tell
        end tell
        '''
        ok, out = _run_applescript(script)
        if not ok:
            return {
                "content": [
                    TextContent(type="text", text=f"Error: {out}")
                ]
            }
        return {
            "content": [
                TextContent(
                    type="text",
                    text=f"Rectangle drawn and text '{text}' added successfully",
                )
            ]
        }
    except Exception as e:
        return {
            "content": [
                TextContent(type="text", text=f"Error: {str(e)}")
            ]
        }


# =========================================================
# RESOURCES
# =========================================================

@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    print("CALLED: get_greeting(name: str) -> str:")
    return f"Hello, {name}!"


# =========================================================
# PROMPTS
# =========================================================

@mcp.prompt()
def review_code(code: str) -> str:
    return f"Please review this code:\n\n{code}"
    print("CALLED: review_code(code: str) -> str:")


@mcp.prompt()
def debug_error(error: str) -> list[base.Message]:
    return [
        base.UserMessage("I'm seeing this error:"),
        base.UserMessage(error),
        base.AssistantMessage("I'll help debug that. What have you tried so far?"),
    ]


if __name__ == "__main__":
    print("STARTING")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Run without transport for dev server
    else:
        mcp.run(transport="stdio")  # Run with stdio for direct execution