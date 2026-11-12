"""Persistent semantic response cache for the Gateway LLM request path."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Awaitable, Callable, Literal, Mapping, cast

from gateway.platform.database import SQLiteDatabase


_SCHEMA = """CREATE TABLE IF NOT EXISTS semantic_cache (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 created_at REAL NOT NULL,
 last_hit_at REAL,
 namespace TEXT NOT NULL,
 scope TEXT NOT NULL DEFAULT '',
 query_text TEXT NOT NULL,
 query_hash TEXT NOT NULL,
 embedding TEXT NOT NULL,
 response_json TEXT NOT NULL,
 hits INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_semantic_cache_lookup
 ON semantic_cache(namespace, scope, created_at DESC);
CREATE TABLE IF NOT EXISTS semantic_cache_stats (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 lookups INTEGER NOT NULL DEFAULT 0,
 hits INTEGER NOT NULL DEFAULT 0,
 misses INTEGER NOT NULL DEFAULT 0,
 skipped INTEGER NOT NULL DEFAULT 0,
 stores INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO semantic_cache_stats (id) VALUES (1);"""

_DEFAULT_NAMESPACE_FIELDS = (
    "model", "provider", "profile", "system", "tools", "response_format", "temperature",
)
EmbeddingTask = Literal["retrieval_document", "retrieval_query"]


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return -1.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return -1.0
    return sum(x * y for x, y in zip(left, right, strict=True)) / (left_norm * right_norm)


@dataclass(frozen=True, slots=True)
class SemanticCacheConfig:
    enabled: bool = True
    default_on: bool = False
    threshold: float = 0.95
    ttl_seconds: int = 3600
    max_entries: int = 5000
    namespace_fields: tuple[str, ...] = _DEFAULT_NAMESPACE_FIELDS
    max_temperature: float = 0.3
    skip_when_tools: bool = True
    skip_when_stream: bool = True
    scope_dimensions: tuple[str, ...] = ("tenant",)
    task_type: EmbeddingTask = "retrieval_query"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SemanticCacheConfig":
        semantic = raw.get("semantic") or {}
        if not isinstance(semantic, Mapping):
            raise ValueError("cache.yaml: semantic must be a mapping")
        task_type = str(semantic.get("task_type", "retrieval_query"))
        if task_type not in {"retrieval_document", "retrieval_query"}:
            raise ValueError("cache.yaml: semantic.task_type must be retrieval_document or retrieval_query")
        config = cls(
            enabled=bool(semantic.get("enabled", True)),
            default_on=bool(semantic.get("default_on", False)),
            threshold=float(semantic.get("threshold", 0.95)),
            ttl_seconds=int(semantic.get("ttl_seconds", 3600)),
            max_entries=int(semantic.get("max_entries", 5000)),
            namespace_fields=tuple(semantic.get("namespace_fields", _DEFAULT_NAMESPACE_FIELDS)),
            max_temperature=float(semantic.get("max_temperature", 0.3)),
            skip_when_tools=bool(semantic.get("skip_when_tools", True)),
            skip_when_stream=bool(semantic.get("skip_when_stream", True)),
            scope_dimensions=tuple(semantic.get("scope_dimensions", ("tenant",))),
            task_type=cast(EmbeddingTask, task_type),
        )
        if not 0.0 <= config.threshold <= 1.0:
            raise ValueError("cache.yaml: semantic.threshold must be between 0 and 1")
        if config.ttl_seconds < 0 or config.max_entries < 0:
            raise ValueError("cache.yaml: semantic ttl_seconds/max_entries cannot be negative")
        return config

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "default_on": self.default_on,
            "threshold": self.threshold,
            "ttl_seconds": self.ttl_seconds,
            "max_entries": self.max_entries,
            "namespace_fields": list(self.namespace_fields),
            "max_temperature": self.max_temperature,
            "skip_when_tools": self.skip_when_tools,
            "skip_when_stream": self.skip_when_stream,
            "scope_dimensions": list(self.scope_dimensions),
            "task_type": self.task_type,
        }


@dataclass(slots=True)
class CacheLookup:
    hit: bool = False
    response: dict[str, Any] | None = None
    embedding: list[float] | None = None
    similarity: float = 0.0
    skipped_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "hit": self.hit,
            "kind": "semantic",
            "similarity": round(self.similarity, 6),
            "skipped_reason": self.skipped_reason,
        }


class SemanticCache:
    """SQLite-backed cache. Database failures deliberately propagate."""

    def __init__(
        self,
        embed: Callable[[str, EmbeddingTask], Awaitable[list[float]]],
        database_path: Path,
        *,
        config: SemanticCacheConfig | None = None,
    ) -> None:
        self._embed = embed
        self.database = SQLiteDatabase(database_path)
        self.config = config or SemanticCacheConfig()
        self.enabled = self.config.enabled
        self.default_on = self.config.default_on
        self.threshold = self.config.threshold
        self.ttl_seconds = self.config.ttl_seconds
        self.database.migrate([_SCHEMA])

    def _namespace(self, fields: Mapping[str, Any]) -> str:
        payload = {
            name: fields.get(name)
            for name in self.config.namespace_fields
            if fields.get(name) is not None
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(encoded).hexdigest()[:32]

    def _scope(self, principal: Mapping[str, str] | None) -> str:
        values = principal or {}
        selected = {name: values.get(name) for name in self.config.scope_dimensions}
        return json.dumps(selected, sort_keys=True) if selected else ""

    def _eligibility(
        self,
        *,
        opt_in: bool | None,
        temperature: float,
        has_tools: bool,
        stream: bool,
    ) -> tuple[bool, str]:
        active = self.default_on if opt_in is None else opt_in
        if not self.enabled:
            return False, "semantic cache disabled"
        if not active:
            return False, "semantic cache not requested"
        if self.config.skip_when_tools and has_tools:
            return False, "requests with tools are not cached"
        if self.config.skip_when_stream and stream:
            return False, "streaming requests are not cached"
        if temperature > self.config.max_temperature:
            return False, "temperature exceeds semantic-cache maximum"
        return True, ""

    async def lookup(
        self,
        prompt: str,
        fields: dict[str, Any],
        *,
        principal: Mapping[str, str] | None = None,
        opt_in: bool | None,
        temperature: float = 0.0,
        has_tools: bool = False,
        stream: bool = False,
    ) -> CacheLookup:
        eligible, reason = self._eligibility(
            opt_in=opt_in, temperature=temperature, has_tools=has_tools, stream=stream,
        )
        if not eligible:
            await asyncio.to_thread(self._bump, "skipped")
            return CacheLookup(skipped_reason=reason)
        embedding = list(await self._embed(prompt, self.config.task_type))
        return await asyncio.to_thread(
            self._lookup_embedding, fields, principal, embedding,
        )

    def _lookup_embedding(
        self,
        fields: dict[str, Any],
        principal: Mapping[str, str] | None,
        embedding: list[float],
    ) -> CacheLookup:
        namespace = self._namespace(fields)
        scope = self._scope(principal)
        query = "SELECT id, embedding, response_json FROM semantic_cache WHERE namespace=? AND scope=?"
        arguments: list[object] = [namespace, scope]
        if self.ttl_seconds:
            query += " AND created_at>=?"
            arguments.append(time.time() - self.ttl_seconds)
        best_id: int | None = None
        best_response: dict[str, Any] | None = None
        best_similarity = -1.0
        with self.database.connect() as connection:
            connection.execute("UPDATE semantic_cache_stats SET lookups=lookups+1 WHERE id=1")
            for row in connection.execute(query, arguments).fetchall():
                candidate = json.loads(str(row["embedding"]))
                similarity = _cosine(embedding, [float(value) for value in candidate])
                if similarity > best_similarity:
                    best_id = int(row["id"])
                    best_response = json.loads(str(row["response_json"]))
                    best_similarity = similarity
            if best_id is not None and best_similarity >= self.threshold:
                connection.execute(
                    "UPDATE semantic_cache SET hits=hits+1,last_hit_at=? WHERE id=?",
                    (time.time(), best_id),
                )
                connection.execute("UPDATE semantic_cache_stats SET hits=hits+1 WHERE id=1")
                return CacheLookup(True, best_response, embedding, best_similarity)
            connection.execute("UPDATE semantic_cache_stats SET misses=misses+1 WHERE id=1")
        return CacheLookup(False, embedding=embedding, similarity=max(0.0, best_similarity))

    def store(
        self,
        prompt: str,
        fields: dict[str, Any],
        response: dict[str, Any],
        embedding: list[float] | None,
        *,
        principal: Mapping[str, str] | None = None,
    ) -> None:
        if embedding is None or not self.enabled:
            return
        namespace = self._namespace(fields)
        scope = self._scope(principal)
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO semantic_cache
                (created_at,namespace,scope,query_text,query_hash,embedding,response_json)
                VALUES (?,?,?,?,?,?,?)""",
                (
                    time.time(), namespace, scope, prompt[:8000],
                    hashlib.sha256(prompt.encode()).hexdigest(),
                    json.dumps([float(value) for value in embedding]),
                    json.dumps(response, default=str),
                ),
            )
            connection.execute("UPDATE semantic_cache_stats SET stores=stores+1 WHERE id=1")
            if self.config.max_entries:
                connection.execute(
                    """DELETE FROM semantic_cache WHERE id IN (
                    SELECT id FROM semantic_cache ORDER BY created_at DESC LIMIT -1 OFFSET ?
                    )""",
                    (self.config.max_entries,),
                )

    def _bump(self, column: str) -> None:
        if column not in {"lookups", "hits", "misses", "skipped", "stores"}:
            raise ValueError(f"unknown semantic cache statistic: {column}")
        with self.database.connect() as connection:
            connection.execute(f"UPDATE semantic_cache_stats SET {column}={column}+1 WHERE id=1")

    def stats(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM semantic_cache_stats WHERE id=1").fetchone()
            if row is None:
                raise RuntimeError("semantic cache statistics row is missing")
            stats = dict(row)
            entries = int(connection.execute("SELECT COUNT(*) FROM semantic_cache").fetchone()[0])
        stats.pop("id", None)
        lookups = int(stats["lookups"])
        return {
            **stats,
            "entries": entries,
            "hit_rate": round(int(stats["hits"]) / lookups, 6) if lookups else 0.0,
            "config": self.config.as_dict(),
        }

    def purge(self, *, expired_only: bool = True) -> int:
        with self.database.connect() as connection:
            if expired_only and not self.ttl_seconds:
                return 0
            if expired_only:
                cursor = connection.execute(
                    "DELETE FROM semantic_cache WHERE created_at<?",
                    (time.time() - self.ttl_seconds,),
                )
            else:
                cursor = connection.execute("DELETE FROM semantic_cache")
            return int(cursor.rowcount)

    def healthcheck(self) -> None:
        """Prove both schema readability and backend writability."""
        with self.database.connect() as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or result[0] != "ok":
                raise RuntimeError("semantic cache database integrity check failed")
            connection.execute("UPDATE semantic_cache_stats SET skipped=skipped WHERE id=1")
