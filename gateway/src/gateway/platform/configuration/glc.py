"""Gateway-owned resolution for the migrated GLC configuration surface."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import os
from pathlib import Path

import yaml


AI_OS_ROOT = Path(__file__).resolve().parents[5]
GATEWAY_CONFIG_ROOT = AI_OS_ROOT / "gateway" / "config"
DATABASE_ROOT = AI_OS_ROOT / "Database" / "sqlite"


class GLCPaths:
    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        env = environment or os.environ
        config_dir = Path(env.get("GLC_CONFIG_DIR", str(GATEWAY_CONFIG_ROOT))).expanduser()
        self.config_dir = config_dir
        self.ledger_db = Path(env.get("GLC_GATEWAY_DB", str(DATABASE_ROOT / "gateway.sqlite"))).expanduser()
        self.audit_db = Path(env.get("GLC_AUDIT_DB", str(DATABASE_ROOT / "audit.sqlite"))).expanduser()

    def load_mapping(self, path: Path) -> dict[str, Any]:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"required configuration does not exist: {path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"configuration is malformed: {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"configuration must be a YAML mapping: {path}")
        return value
