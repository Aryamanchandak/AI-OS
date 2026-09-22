"""Fail-fast startup dependency checks with machine-readable failures."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import json


@dataclass(frozen=True, slots=True)
class StartupCheck:
    dependency: str
    check: Callable[[], None]


class StartupDependencyError(RuntimeError):
    def __init__(self, dependency: str, cause: BaseException) -> None:
        self.dependency = dependency
        self.cause = cause
        self.event = {
            "event": "gateway.startup.dependency_failed",
            "dependency": dependency,
            "error_type": type(cause).__name__,
            "error": str(cause),
        }
        super().__init__(json.dumps(self.event, sort_keys=True))


def run_startup_checks(checks: Iterable[StartupCheck]) -> None:
    for item in checks:
        try:
            item.check()
        except BaseException as exc:
            raise StartupDependencyError(item.dependency, exc) from exc
