"""Entry point: `python -m simple_server` (stdio transport)."""

from .app import mcp
from . import tools  # noqa: F401  -- importing registers every tool

if __name__ == "__main__":
    mcp.run()
