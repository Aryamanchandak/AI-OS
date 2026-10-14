import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from . import geometry, draw_engine, config

app = Server("paint-automation-server")

# Session state — persists across tool calls within one server process
_center: tuple | None = None
_shape_bounds: dict = {}


# ---------------------------------------------------------------------------
# Tool: open_drawing_app
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "open_drawing_app":
        result = draw_engine.open_drawing_app(arguments.get("app_name"))
        return [types.TextContent(type="text", text=result)]

    if name == "set_canvas_corners":
        global _center
        corners = {
            "top_left":     (arguments["top_left_x"],     arguments["top_left_y"]),
            "top_right":    (arguments["top_right_x"],    arguments["top_right_y"]),
            "bottom_left":  (arguments["bottom_left_x"],  arguments["bottom_left_y"]),
            "bottom_right": (arguments["bottom_right_x"], arguments["bottom_right_y"]),
        }
        _center = geometry.compute_center(corners)
        return [types.TextContent(type="text", text=f"Canvas set. Center computed at {_center}")]

    if name == "draw_circle":
        _require_center()
        radius = arguments["radius"]
        bounds = geometry.get_circle_bounds(_center, radius)
        _shape_bounds["circle"] = bounds
        result = draw_engine.draw_circle_on_screen(_center, radius)
        return [types.TextContent(type="text", text=result)]

    if name == "draw_square":
        _require_center()
        side = arguments["side_length"]
        bounds = geometry.get_square_bounds(_center, side)
        _shape_bounds["square"] = bounds
        result = draw_engine.draw_square_on_screen(bounds["top_left"], bounds["bottom_right"])
        return [types.TextContent(type="text", text=result)]

    if name == "draw_rectangle":
        _require_center()
        bounds = geometry.get_rectangle_bounds(_center, arguments["width"], arguments["height"])
        _shape_bounds["rectangle"] = bounds
        result = draw_engine.draw_rectangle_on_screen(bounds["top_left"], bounds["bottom_right"])
        return [types.TextContent(type="text", text=result)]

    if name == "add_text":
        shape_key = arguments["inside_shape"]
        if shape_key not in _shape_bounds:
            return [types.TextContent(type="text", text=f"Error: '{shape_key}' has not been drawn yet.")]
        bounds = _shape_bounds[shape_key]
        position = geometry.get_text_origin(bounds, inset=20)
        result = draw_engine.add_text_on_screen(
            position=position,
            text=arguments["text"],
            font_name=arguments.get("font_name", "Arial"),
            font_size=arguments.get("font_size", 24),
            shape_bounds=bounds,
        )
        return [types.TextContent(type="text", text=result)]

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


def _require_center():
    if _center is None:
        raise ValueError("set_canvas_corners must be called before drawing.")


# ---------------------------------------------------------------------------
# Tool listing
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="open_drawing_app",
            description=(
                "Opens the drawing application on macOS and waits for it to be ready. "
                "MUST be called first before any drawing operations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "App to open: 'libreoffice_draw' (default), 'keynote', or 'paintbrush'.",
                    }
                },
            },
        ),
        types.Tool(
            name="set_canvas_corners",
            description=(
                "Defines the drawable canvas area using 4 corner pixel coordinates. "
                "Automatically computes and stores the center point. "
                "MUST be called before draw_circle, draw_square, or draw_rectangle."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "top_left_x":     {"type": "integer"},
                    "top_left_y":     {"type": "integer"},
                    "top_right_x":    {"type": "integer"},
                    "top_right_y":    {"type": "integer"},
                    "bottom_left_x":  {"type": "integer"},
                    "bottom_left_y":  {"type": "integer"},
                    "bottom_right_x": {"type": "integer"},
                    "bottom_right_y": {"type": "integer"},
                },
                "required": [
                    "top_left_x", "top_left_y",
                    "top_right_x", "top_right_y",
                    "bottom_left_x", "bottom_left_y",
                    "bottom_right_x", "bottom_right_y",
                ],
            },
        ),
        types.Tool(
            name="draw_circle",
            description=(
                "Draws a circle centered on the canvas center point. "
                "Requires open_drawing_app and set_canvas_corners to be called first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "radius": {"type": "integer", "description": "Radius in pixels."}
                },
                "required": ["radius"],
            },
        ),
        types.Tool(
            name="draw_square",
            description=(
                "Draws a square centered on the canvas center point. "
                "Requires open_drawing_app and set_canvas_corners to be called first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "side_length": {"type": "integer", "description": "Length of each side in pixels."}
                },
                "required": ["side_length"],
            },
        ),
        types.Tool(
            name="draw_rectangle",
            description=(
                "Draws a rectangle centered on the canvas center point. "
                "Requires open_drawing_app and set_canvas_corners to be called first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "width":  {"type": "integer", "description": "Total width in pixels."},
                    "height": {"type": "integer", "description": "Total height in pixels."},
                },
                "required": ["width", "height"],
            },
        ),
        types.Tool(
            name="add_text",
            description=(
                "Adds text inside one of the previously drawn shapes. "
                "Call AFTER drawing the target shape. "
                "inside_shape must be 'circle', 'square', or 'rectangle'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text":         {"type": "string", "description": "The string to write."},
                    "font_name":    {"type": "string", "description": "Font family, e.g. 'Arial', 'Georgia'."},
                    "font_size":    {"type": "integer", "description": "Size in points, e.g. 24."},
                    "inside_shape": {
                        "type": "string",
                        "enum": ["circle", "square", "rectangle"],
                        "description": "Which drawn shape to write inside.",
                    },
                },
                "required": ["text", "font_name", "font_size", "inside_shape"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(stdio_server(app))
