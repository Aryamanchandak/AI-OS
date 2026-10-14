"""A simple, minimal MCP server for the ReAct loop.

Only depends on `mcp` (already in this project's venv). To add a tool: drop a
module in `simple_server/tools/` and decorate a function with `@mcp.tool()`.
The tools package auto-imports every module, so there is nothing else to wire.

Run it standalone:  python -m simple_server
The loop launches it automatically (see react_loop/config.py defaults).
"""

from .app import mcp

__all__ = ["mcp"]
