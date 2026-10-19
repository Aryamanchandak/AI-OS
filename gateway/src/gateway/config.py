"""The one YAML loader: every config file is read through `load_mapping`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_mapping(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"required configuration does not exist: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"configuration is malformed: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"configuration must be a YAML mapping: {path}")
    return value
