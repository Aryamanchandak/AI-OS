"""
Central plugin registry.
Each group module calls @register(...) on its tools.
mcp_server.py reads get_all() once at startup.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class ToolEntry:
    fn: Callable
    group: str


_REGISTRY: list[ToolEntry] = []


def register(group: str):
    """
    Decorator — add a tool function to the MCP registry.

    @register(group="finance")
    def generate_credit_one_pager(...):
        ...
    """
    def decorator(fn: Callable) -> Callable:
        for entry in _REGISTRY:
            if entry.fn is fn and entry.group == group:
                logger.debug("Skipped duplicate registration for tool '%s'", fn.__name__)
                return fn
        _REGISTRY.append(ToolEntry(fn=fn, group=group))
        logger.debug("Registered tool '%s' in group '%s'", fn.__name__, group)
        return fn
    return decorator


def get_all() -> list[ToolEntry]:
    return list(_REGISTRY)


def get_by_group(group: str) -> list[ToolEntry]:
    return [e for e in _REGISTRY if e.group == group]


def assert_no_name_collisions():
    """Call once at startup. Raises if two registry tools share a name."""
    seen: dict[str, str] = {}
    for entry in _REGISTRY:
        name = entry.fn.__name__
        if name in seen:
            raise RuntimeError(
                f"Tool name collision: '{name}' registered in both "
                f"'{seen[name]}' and '{entry.group}'"
            )
        seen[name] = entry.group
