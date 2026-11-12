"""Small configuration seam used by moved channel setup tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from gateway.platform.configuration.glc import DATABASE_ROOT, GATEWAY_CONFIG_ROOT

CONFIG_DIR = Path(os.getenv("GLC_CONFIG_DIR", str(GATEWAY_CONFIG_ROOT))).expanduser()
SECRET_ROOT = Path(
    os.getenv("GLC_CHANNEL_SECRETS_DIR", str(DATABASE_ROOT / "channel_secrets"))
).expanduser()


def load_channels() -> dict[str, Any]:
    path = Path(os.getenv("GLC_CHANNELS_YAML", str(CONFIG_DIR / "channels.yaml"))).expanduser()
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, yaml.YAMLError):
        return {"defaults": {}, "channels": {}}
    return value if isinstance(value, dict) else {"defaults": {}, "channels": {}}
