"""Semantic response cache that reuses the lookup embedding on a miss."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import threading
import time
from typing import Any, Awaitable, Callable


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left: return -1.0
    denom = math.sqrt(sum(x*x for x in left)) * math.sqrt(sum(x*x for x in right))
    return sum(x*y for x, y in zip(left, right)) / denom if denom else -1.0


@dataclass(slots=True)
class CacheLookup:
    hit: bool = False; response: dict[str, Any] | None = None
    embedding: list[float] | None = None; similarity: float = 0.0
    def as_dict(self) -> dict[str, Any]: return {"hit": self.hit, "kind": "semantic", "similarity": round(self.similarity, 6)}


class SemanticCache:
    def __init__(self, embed: Callable[[str], Awaitable[list[float]]], *, threshold: float = .95, ttl_seconds: int = 3600, enabled: bool = True, default_on: bool = False) -> None:
        self._embed = embed; self.threshold = threshold; self.ttl_seconds = ttl_seconds; self.enabled = enabled; self.default_on = default_on
        self._entries: list[dict[str, Any]] = []; self._lock = threading.Lock(); self._lookups = self._hits = 0

    async def lookup(self, prompt: str, fields: dict[str, Any], *, opt_in: bool | None, eligible: bool = True) -> CacheLookup:
        active = self.default_on if opt_in is None else opt_in
        if not self.enabled or not active or not eligible: return CacheLookup()
        vector = await self._embed(prompt); namespace = json.dumps(fields, sort_keys=True, default=str); now = time.time(); best = None; score = -1.0
        with self._lock:
            self._lookups += 1
            self._entries[:] = [x for x in self._entries if not self.ttl_seconds or now - x["created"] <= self.ttl_seconds]
            for item in self._entries:
                if item["namespace"] == namespace and (candidate := _cosine(vector, item["embedding"])) > score: score, best = candidate, item
            if best is not None and score >= self.threshold: self._hits += 1; return CacheLookup(True, dict(best["response"]), vector, score)
        return CacheLookup(False, embedding=vector, similarity=max(0.0, score))

    def store(self, fields: dict[str, Any], response: dict[str, Any], embedding: list[float] | None) -> None:
        if embedding is None: return
        with self._lock: self._entries.append({"namespace": json.dumps(fields, sort_keys=True, default=str), "response": dict(response), "embedding": list(embedding), "created": time.time()})

    def stats(self) -> dict[str, Any]:
        with self._lock: return {"entries": len(self._entries), "lookups": self._lookups, "hits": self._hits, "hit_rate": self._hits / self._lookups if self._lookups else 0.0}

    def purge(self, *, expired_only: bool = True) -> int:
        with self._lock:
            before = len(self._entries)
            if expired_only and self.ttl_seconds: self._entries[:] = [x for x in self._entries if time.time() - x["created"] <= self.ttl_seconds]
            elif not expired_only: self._entries.clear()
            return before - len(self._entries)
