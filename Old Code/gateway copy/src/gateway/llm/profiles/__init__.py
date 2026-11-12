"""Versioned exact provider/model profile pins."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ProfileError(ValueError):
    pass


class ProfileRegistry:
    def __init__(self, values: dict[str, dict[str, dict[str, Any]]]) -> None:
        self._values = values

    @classmethod
    def from_yaml(cls, path: Path) -> "ProfileRegistry":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if raw.get("version") != 1:
            raise ProfileError(f"{path}: version must be 1")
        values: dict[str, dict[str, dict[str, Any]]] = {}
        for kind in ("chat", "embedding"):
            entries = raw.get(kind)
            if not isinstance(entries, dict) or not entries:
                raise ProfileError(f"{path}: `{kind}` must be a non-empty mapping")
            values[kind] = {}
            for name, value in entries.items():
                if not isinstance(value, dict):
                    raise ProfileError(f"{path}: {kind}.{name} must be a mapping")
                required = {"provider", "model"} | ({"dim"} if kind == "embedding" else set())
                missing = sorted(required - value.keys())
                if missing:
                    raise ProfileError(f"{path}: {kind}.{name} is missing {missing}")
                spec = dict(value)
                if not all(isinstance(spec[x], str) and spec[x].strip() for x in ("provider", "model")):
                    raise ProfileError(f"{path}: {kind}.{name} has an invalid pin")
                if "tier" in spec or "route" in spec:
                    raise ProfileError(f"{path}: {kind}.{name} must be pinned, not routed")
                if kind == "embedding" and (isinstance(spec["dim"], bool) or not isinstance(spec["dim"], int) or spec["dim"] <= 0):
                    raise ProfileError(f"{path}: embedding.{name}.dim must be a positive integer")
                values[kind][str(name)] = spec
        return cls(values)

    def resolve(self, kind: str, name: str) -> dict[str, Any]:
        try:
            return dict(self._values[kind][name])
        except KeyError as exc:
            known = sorted(self._values.get(kind, {}))
            raise ProfileError(f"unknown {kind} profile '{name}'. Try one of: {known}") from exc

    def all(self, kind: str) -> dict[str, dict[str, Any]]:
        return {name: dict(spec) for name, spec in self._values[kind].items()}
