from __future__ import annotations

from collections.abc import Iterable


DEFAULT_ALLOWED_CONSUMERS: tuple[str, ...] = ("kg", "sqlite", "vector")


def default_allowed_consumers() -> list[str]:
    """Return a fresh default access list for one captured item."""

    return list(DEFAULT_ALLOWED_CONSUMERS)


def resolve_targets(
    *,
    allowed_consumers: Iterable[str],
    registered_consumers: Iterable[str],
) -> tuple[str, ...]:
    """Resolve every registered target permitted by access control.

    Source type is deliberately absent: it is provenance and never affects
    routing. Returning a stable order keeps dispatch and its audit trail
    deterministic.
    """

    allowed = set(allowed_consumers)
    registered = set(registered_consumers)
    return tuple(sorted(allowed & registered))
