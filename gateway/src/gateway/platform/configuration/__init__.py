"""Typed loading for non-domain Gateway configuration."""

from gateway.platform.configuration.settings import GatewaySettings, load_gateway_settings
from gateway.platform.configuration.glc import DATABASE_ROOT, GATEWAY_CONFIG_ROOT, GLCPaths

__all__ = [
    "DATABASE_ROOT",
    "GATEWAY_CONFIG_ROOT",
    "GLCPaths",
    "GatewaySettings",
    "load_gateway_settings",
]
