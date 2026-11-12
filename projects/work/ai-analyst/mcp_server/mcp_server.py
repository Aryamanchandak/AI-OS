"""
ICICI Prudential MCP Server — entry point.
All tool registration happens inside tools/.
This file only bootstraps the environment, wires the registry into FastMCP, and runs.
"""
import importlib.util
import json
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.abspath(__file__))

# ── Path setup (must happen before any group imports) ────────────────────────
sys.path.insert(0, os.path.join(_ROOT, "backend"))
# agent provides memory.py, vector_index.py, schemas.py, gateway.py,
# and artifacts.py — imported by tools/knowledge/memory_tools.py.
sys.path.insert(0, os.path.join(os.path.dirname(_ROOT), "agent"))

# Bootstrap the research_tools package from its folder.
_RESEARCH_DIR = os.path.join(_ROOT, "research_tools")
_spec = importlib.util.spec_from_file_location(
    "research_tools",
    os.path.join(_RESEARCH_DIR, "__init__.py"),
    submodule_search_locations=[_RESEARCH_DIR],
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["research_tools"] = _mod
_spec.loader.exec_module(_mod)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ICICI Prudential Agent Tools")

# Shim — credit_one_pager_mcp and lease_deed_mcp do `from mcp_server import mcp`.
# Must be set before groups/ is imported.
sys.modules.setdefault("mcp_server", sys.modules[__name__])

# ── Import all groups — triggers @register() and shim-based @mcp.tool() calls ──
# We load tools/__init__.py explicitly as "groups" for two reasons:
# 1. backend/tools/ shadows the real tools/ in sys.path when running as a script.
# 2. tools/__init__.py calls importlib.import_module("groups.<name>"), so the
#    package must be registered under the name "groups" in sys.modules.
import importlib.util as _ilu
_gdir = os.path.join(_ROOT, "tools")
_gspec = _ilu.spec_from_file_location(
    "groups",
    os.path.join(_gdir, "__init__.py"),
    submodule_search_locations=[_gdir],
)
_gmod = _ilu.module_from_spec(_gspec)
sys.modules["groups"] = _gmod
_gspec.loader.exec_module(_gmod)
del _ilu, _gdir, _gspec, _gmod

# ── Pull every registry tool into FastMCP ────────────────────────────────────
from tool_registry import get_all, assert_no_name_collisions

assert_no_name_collisions()

# Guard against a shim tool silently overwriting a registry tool (or vice versa).
_shim_names = set(mcp._tool_manager._tools.keys())
for entry in get_all():
    if entry.fn.__name__ in _shim_names:
        raise RuntimeError(
            f"Tool name collision: registry tool '{entry.fn.__name__}' (group '{entry.group}') "
            f"already registered as a shim tool"
        )

for entry in get_all():
    mcp.tool()(entry.fn)

logger.info(
    "MCP server ready — %d tools registered across %d groups",
    len(get_all()),
    len({e.group for e in get_all()}),
)


@mcp.tool()
def list_tools() -> str:
    """Returns all registered tools grouped by domain. Useful for agent introspection."""
    registry_groups = {e.fn.__name__: e.group for e in get_all()}
    grouped: dict[str, list[str]] = {}
    for name in sorted(mcp._tool_manager._tools):
        group = registry_groups.get(name, "other")
        grouped.setdefault(group, []).append(name)
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
