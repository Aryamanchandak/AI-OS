"""Concurrency-safe in-memory usage rollups; audit remains the durable event record."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any

DIMENSIONS = ("tenant", "project", "user", "agent", "session")


@dataclass(frozen=True, slots=True)
class Principal:
    tenant: str | None = None; project: str | None = None; user: str | None = None
    agent: str | None = None; session: str | None = None

    @classmethod
    def from_request(cls, request: Any) -> "Principal":
        return cls(**{name: getattr(request, name, None) for name in DIMENSIONS})

    def present(self) -> dict[str, str]:
        return {name: value for name in DIMENSIONS if (value := getattr(self, name)) is not None}


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0; output_tokens: int = 0
    cache_creation_input_tokens: int = 0; cache_read_input_tokens: int = 0


class Meter:
    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []; self._lock = threading.Lock()

    def record(self, **record: Any) -> None:
        with self._lock: self._records.append({"timestamp": time.time(), **record})

    def recent(self, limit: int = 100, provider: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock: rows = list(reversed(self._records))
        return [x for x in rows if (provider is None or x.get("provider") == provider) and (status is None or x.get("status") == status)][:limit]

    def aggregate(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        with self._lock: rows = list(self._records)
        for row in rows:
            key = str(row.get("provider", "unknown")); item = out.setdefault(key, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "dollars": 0.0})
            item["calls"] += 1; item["input_tokens"] += int(row.get("input_tokens", 0)); item["output_tokens"] += int(row.get("output_tokens", 0)); item["dollars"] += float(row.get("cost_usd", 0))
        return out

    def rollup(self, dimension: str, *, value: str | None = None, since: float = 0, group_by_provider: bool = True) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        with self._lock: rows = list(self._records)
        for row in rows:
            principal = row.get("principal") or {}; dim_value = principal.get(dimension)
            if row["timestamp"] < since or dim_value is None or (value is not None and dim_value != value): continue
            provider = str(row.get("provider")) if group_by_provider else "*"; key = (dim_value, provider)
            item = grouped.setdefault(key, {"dimension": dimension, "value": dim_value, "provider": provider, "calls": 0, "dollars": 0.0})
            item["calls"] += 1; item["dollars"] += float(row.get("cost_usd", 0))
        return list(grouped.values())

    def rollup_all(self, *, since: float = 0) -> dict[str, list[dict[str, Any]]]:
        return {dim: self.rollup(dim, since=since) for dim in DIMENSIONS}
