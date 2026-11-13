"""Where this project keeps its runtime files. One place, so `state/` is easy to wipe."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(exist_ok=True)
GATEWAY_DIR = ROOT / "llm_gateway"
MCP_SERVER = ROOT / "mcp_server.py"
