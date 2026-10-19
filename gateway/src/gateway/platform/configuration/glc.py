"""Gateway-owned resolution for the migrated GLC configuration surface."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path


AI_OS_ROOT = Path(__file__).resolve().parents[5]
GATEWAY_CONFIG_ROOT = AI_OS_ROOT / "gateway" / "config"
DATABASE_ROOT = AI_OS_ROOT / "Database" / "sqlite"


class GLCPaths:
    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        env = environment or os.environ
        config_dir = Path(env.get("GLC_CONFIG_DIR", str(GATEWAY_CONFIG_ROOT))).expanduser()
        self.config_dir = config_dir
        self.ledger_db = Path(env.get("GLC_GATEWAY_DB", str(DATABASE_ROOT / "gateway.sqlite"))).expanduser()
