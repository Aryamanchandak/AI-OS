"""Where this project keeps its runtime files. One place, so `state/` is easy to wipe."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# A07_STATE_DIR points the agent at a different state folder, e.g. an empty
# one, to show what it answers without the indexed corpus.
STATE_DIR = Path(os.getenv("A07_STATE_DIR") or ROOT / "state")
STATE_DIR.mkdir(exist_ok=True)
MCP_SERVER = ROOT / "mcp_server.py"
