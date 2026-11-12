# credit_one_pager_mcp does `from mcp_server import mcp` and uses @mcp.tool().
# Importing it here triggers that auto-registration onto the shim — no registry needed.
import credit_one_pager_mcp  # noqa: F401
