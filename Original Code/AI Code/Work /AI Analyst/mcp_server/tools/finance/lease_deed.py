# lease_deed_mcp does `from mcp_server import mcp` and uses @mcp.tool().
# Importing it here triggers that auto-registration onto the shim — no registry needed.
import lease_deed_mcp  # noqa: F401
