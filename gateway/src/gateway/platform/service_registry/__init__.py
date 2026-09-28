"""Validated, non-secret addresses for AI OS services."""

from gateway.platform.service_registry.registry import (
    DEFAULT_REGISTRY_PATH,
    ServiceDefinition,
    ServiceRegistry,
    gateway_address,
    load_service_registry,
)

__all__ = ["DEFAULT_REGISTRY_PATH", "ServiceDefinition", "ServiceRegistry", "gateway_address", "load_service_registry"]
