"""Validated Gateway process configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
import yaml


class GatewaySettings(BaseModel):
    """Non-secret settings owned by the Gateway process."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str
    port: int = Field(ge=1, le=65535)
    log_level: Literal["critical", "error", "warning", "info", "debug", "trace"]

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        host = value.strip()
        if not host or "://" in host or "/" in host or any(char.isspace() for char in host):
            raise ValueError("host must be a hostname or IP address without a URL scheme")
        return host


def load_gateway_settings(path: Path) -> GatewaySettings:
    """Load required process settings, failing eagerly on missing/bad YAML."""

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Gateway configuration does not exist: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Gateway configuration is malformed: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Gateway configuration must be a YAML mapping: {path}")
    return GatewaySettings.model_validate(raw)
