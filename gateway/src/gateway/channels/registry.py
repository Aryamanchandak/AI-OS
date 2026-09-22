"""Discover adapter modules under gateway/channels/catalogue/<name>/adapter.py.

An adapter module is registered if it exposes a `class Adapter(ChannelAdapter)`.
Registration is best-effort: a broken adapter logs a warning and is skipped
so one broken adapter cannot prevent the gateway from booting.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Any

from gateway.channels.base import ChannelAdapter

CATALOGUE_PACKAGE = "gateway.channels.catalogue"


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    adapters: dict[str, type[ChannelAdapter]]
    failures: dict[str, str]


def discover_with_failures() -> DiscoveryResult:
    adapters: dict[str, type[ChannelAdapter]] = {}
    failures: dict[str, str] = {}
    pkg = importlib.import_module(CATALOGUE_PACKAGE)
    for _, name, ispkg in pkgutil.iter_modules(pkg.__path__):
        if not ispkg:
            continue
        try:
            mod = importlib.import_module(f"{CATALOGUE_PACKAGE}.{name}.adapter")
            cls = getattr(mod, "Adapter", None)
            if isinstance(cls, type) and issubclass(cls, ChannelAdapter):
                adapters[name] = cls
            else:
                failures[name] = "adapter.py does not expose Adapter(ChannelAdapter)"
        except Exception as exc:  # optional integrations fail independently
            failures[name] = f"{type(exc).__name__}: {exc}"
    return DiscoveryResult(adapters=adapters, failures=failures)


def discover() -> dict[str, type[ChannelAdapter]]:
    """Returns {channel_name: Adapter class}. Channels whose adapter is
    still a stub (raises NotImplementedError at class load time)
    register fine; instantiation works, calls fail with a clear message."""
    return discover_with_failures().adapters


def get(name: str) -> type[ChannelAdapter] | None:
    return discover().get(name)


def list_channels() -> list[str]:
    return sorted(discover().keys())


def instantiate(name: str, config: dict[str, Any] | None = None) -> ChannelAdapter:
    cls = get(name)
    if cls is None:
        raise KeyError(f"unknown channel '{name}'")
    return cls(config=config)
