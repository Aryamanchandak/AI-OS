"""
ICICI Prudential MCP Server — entry point.
All tool registration happens inside tools/ (one folder per tool).
This file only bootstraps the environment, wires the registry into FastMCP, and runs.
"""
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _find_workspace_root() -> Path:
    """Locate the AI Code workspace that holds this server and AI Agent."""
    env = os.environ.get("AI_CODE_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(_ROOT).resolve()
    for parent in here.parents:
        if (parent / "mcp_server").is_dir() and (parent / "AI Agent" / "src" / "agent").is_dir():
            return parent
    raise RuntimeError(
        "Could not locate the AI Code workspace root. Set AI_CODE_ROOT to the "
        "directory containing both 'mcp_server' and 'AI Agent/src/agent'."
    )


# ── Path setup (must happen before any group imports) ────────────────────────
sys.path.insert(0, _ROOT)
# The sibling `AI Agent` project provides the shared agent package used by
# tools/knowledge/memory/tool.py.
sys.path.insert(0, str(_find_workspace_root() / "AI Agent" / "src"))
# The sibling `Learning System` project provides the study_system package
# used by tools/study/logic.py. It is not pip-installed here (kept a plain
# sys.path entry, same as AI Agent above, since its own editable install
# already needs this workaround in some environments).
sys.path.insert(0, str(_find_workspace_root() / "Learning System" / "src"))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ICICI Prudential Agent Tools")

# ── Import every tool — triggers @register() calls ───────────────────────────
# The single `tools/` root auto-discovers each group and, within it, each tool
# subpackage; importing them runs their register(group=...) calls.
import tools  # noqa: F401

# ── Pull every registry tool into FastMCP ────────────────────────────────────
from tool_registry import get_all, assert_no_name_collisions

assert_no_name_collisions()

entries = get_all()

for entry in entries:
    mcp.tool()(entry.fn)

logger.info(
    "MCP server ready — %d tools registered across %d groups",
    len(entries),
    len({e.group for e in entries}),
)


@mcp.tool()
def list_tools() -> str:
    """Returns all registered tools grouped by domain. Useful for agent introspection."""
    grouped: dict[str, list[str]] = {}
    for entry in sorted(get_all(), key=lambda e: (e.group, e.fn.__name__)):
        grouped.setdefault(entry.group, []).append(entry.fn.__name__)
    grouped.setdefault("utility", []).append("list_tools")
    return json.dumps(grouped, indent=2)


if __name__ == "__main__":
    import argparse
    import shutil
    import subprocess

    parser = argparse.ArgumentParser(description="ICICI Prudential MCP Server")
    parser.add_argument("--dev", action="store_true", help="Open MCP Inspector")
    args = parser.parse_args()

    if args.dev:
        npx = shutil.which("npx")
        if not npx:
            try:
                import nodejs_wheel
                npx = os.path.join(os.path.dirname(nodejs_wheel.__file__), "bin", "npx")
            except ImportError:
                print("Error: npx not found. Install Node.js or nodejs-wheel-binaries.")
                sys.exit(1)
        subprocess.run([npx, "@modelcontextprotocol/inspector",
                        sys.executable, os.path.abspath(__file__)])
    else:
        mcp.run()
