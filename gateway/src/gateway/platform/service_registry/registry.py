"""Service registry loading, environment overrides, and safe diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
import yaml


_SERVICE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class ServiceDefinition(BaseModel):
    """One resolved service endpoint; this model deliberately has no secrets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str
    port: int = Field(ge=1, le=65535)
    enabled: bool = True
    required: bool = False

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        host = value.strip()
        if not host or "://" in host or "/" in host or any(char.isspace() for char in host):
            raise ValueError("host must be a hostname or IP address without a URL scheme")
        return host

    @property
    def url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"


class _RegistryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    services: dict[str, ServiceDefinition]

    @field_validator("services")
    @classmethod
    def validate_names(
        cls, value: dict[str, ServiceDefinition]
    ) -> dict[str, ServiceDefinition]:
        invalid = sorted(name for name in value if not _SERVICE_NAME.fullmatch(name))
        if invalid:
            raise ValueError(f"invalid service names: {', '.join(invalid)}")
        if not value:
            raise ValueError("at least one service must be configured")
        return value


class ServiceRegistry:
    """Immutable lookup for validated service endpoints."""

    def __init__(self, services: Mapping[str, ServiceDefinition]) -> None:
        self._services = dict(services)
        self._validate_unique_enabled_ports()

    def _validate_unique_enabled_ports(self) -> None:
        owners: dict[int, str] = {}
        for name, service in self._services.items():
            if not service.enabled:
                continue
            previous = owners.get(service.port)
            if previous is not None:
                raise ValueError(
                    "duplicate enabled service port "
                    f"{service.port}: {previous!r} and {name!r}"
                )
            owners[service.port] = name

    def get(self, name: str) -> ServiceDefinition:
        try:
            return self._services[name]
        except KeyError as exc:
            raise KeyError(f"unknown service: {name}") from exc

    def url_for(self, name: str) -> str:
        service = self.get(name)
        if not service.enabled:
            raise ValueError(f"service is disabled: {name}")
        return service.url

    def diagnostics(self) -> dict[str, dict[str, object]]:
        """Return an allow-listed view that cannot expose secret settings."""

        return {
            name: {
                "enabled": service.enabled,
                "required": service.required,
                "address": service.url,
            }
            for name, service in sorted(self._services.items())
        }


def _environment_key(service_name: str, field: str) -> str:
    return f"AI_OS_SERVICE_{service_name.upper()}_{field.upper()}"


def _parse_bool(value: str, *, key: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean")


def _apply_overrides(
    services: Mapping[str, ServiceDefinition], environment: Mapping[str, str]
) -> dict[str, ServiceDefinition]:
    resolved: dict[str, ServiceDefinition] = {}
    for name, service in services.items():
        values: dict[str, Any] = service.model_dump()
        host_key = _environment_key(name, "host")
        port_key = _environment_key(name, "port")
        enabled_key = _environment_key(name, "enabled")
        if host_key in environment:
            values["host"] = environment[host_key]
        if port_key in environment:
            values["port"] = environment[port_key]
        if enabled_key in environment:
            values["enabled"] = _parse_bool(environment[enabled_key], key=enabled_key)
        resolved[name] = ServiceDefinition.model_validate(values)
    return resolved


def load_service_registry(
    path: Path, *, environment: Mapping[str, str] | None = None
) -> ServiceRegistry:
    """Load canonical YAML defaults and apply validated per-service overrides."""

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Service registry does not exist: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Service registry is malformed: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Service registry must be a YAML mapping: {path}")
    document = _RegistryDocument.model_validate(raw)
    services = _apply_overrides(document.services, environment or os.environ)
    return ServiceRegistry(services)
