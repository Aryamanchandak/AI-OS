"""Where the gateway finds its files: `.env`, the YAML config folder and the ledger database.

The only file that imports PyYAML or python-dotenv.
"""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import yaml


GATEWAY_ROOT = Path(__file__).resolve().parents[2]
AI_OS_ROOT = GATEWAY_ROOT.parent
ENV_FILE = GATEWAY_ROOT / ".env"


def load_env() -> None:
    """Read `gateway/.env` if it exists; variables already set in the shell win."""
    load_dotenv(ENV_FILE, override=False)


def load_mapping(path: Path) -> dict[str, Any]:
    """Read one YAML config file, with an error that names the file."""
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"required configuration does not exist: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"configuration is malformed: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"configuration must be a YAML mapping: {path}")
    return value


class Paths:
    """Config folder and ledger database, each overridable by an environment variable."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        env = os.environ if environment is None else environment
        self.config_dir = Path(env.get("GLC_CONFIG_DIR", str(GATEWAY_ROOT / "config"))).expanduser()
        self.ledger_db = Path(
            env.get("GLC_GATEWAY_DB", str(AI_OS_ROOT / "Database" / "sqlite" / "gateway.sqlite"))
        ).expanduser()
