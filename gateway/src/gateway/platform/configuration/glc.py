"""Gateway-owned resolution for the migrated GLC configuration surface."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import os
from pathlib import Path
import secrets

import yaml


AI_OS_ROOT = Path(__file__).resolve().parents[5]
GATEWAY_CONFIG_ROOT = AI_OS_ROOT / "gateway" / "config"
DATABASE_ROOT = AI_OS_ROOT / "Database" / "sqlite"


class GLCPaths:
    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        env = environment or os.environ
        config_dir = Path(env.get("GLC_CONFIG_DIR", str(GATEWAY_CONFIG_ROOT))).expanduser()
        self.config_dir = config_dir
        self.policy = Path(env.get("GLC_POLICY_YAML", str(config_dir / "policy.yaml"))).expanduser()
        self.channels = Path(env.get("GLC_CHANNELS_YAML", str(config_dir / "channels.yaml"))).expanduser()
        self.ledger_db = Path(env.get("GLC_GATEWAY_DB", str(DATABASE_ROOT / "gateway.sqlite"))).expanduser()
        self.audit_db = Path(env.get("GLC_AUDIT_DB", str(DATABASE_ROOT / "audit.sqlite"))).expanduser()
        self.pairing_db = Path(env.get("GLC_PAIRING_DB", str(DATABASE_ROOT / "pairings.sqlite"))).expanduser()
        self.cache_db = Path(env.get("GLC_CACHE_DB", str(DATABASE_ROOT / "semantic_cache.sqlite"))).expanduser()
        self.install_token = Path(
            env.get("GLC_INSTALL_TOKEN_FILE", str(DATABASE_ROOT / "glc_install_token"))
        ).expanduser()

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

    def get_or_create_install_token(self) -> str:
        self.install_token.parent.mkdir(parents=True, exist_ok=True)
        if self.install_token.exists():
            token = self.install_token.read_text(encoding="utf-8").strip()
            if token:
                return token
        token = secrets.token_urlsafe(32)
        self.install_token.write_text(token, encoding="utf-8")
        try:
            os.chmod(self.install_token, 0o600)
        except OSError:
            pass
        return token
