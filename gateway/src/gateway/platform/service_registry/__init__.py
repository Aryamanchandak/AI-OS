"""Validated, non-secret addresses for AI OS services."""

from gateway.platform.service_registry.registry import (
    ServiceDefinition,
    ServiceRegistry,
    load_service_registry,
)

__all__ = ["ServiceDefinition", "ServiceRegistry", "load_service_registry"]
