"""The one shared FastMCP instance.

Kept in its own module so tool files can `from simple_server.app import mcp`
without any circular-import dance. Everything else just registers onto this.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("react-loop-tools")
