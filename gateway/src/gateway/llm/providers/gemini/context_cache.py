"""Gemini explicit context caching.

A long cacheable system prompt is minted once as a `cachedContents` resource and
referenced by name on later calls, so its tokens bill at the cache rate instead
of in full every turn. Ported from `glc_v5/glc/cache/gemini.py`.

Failures are deliberately soft: a cache that cannot be minted returns
`(None, 0)` and the caller sends the prompt inline, which is correct but more
expensive. A caching outage must not become a chat outage.
"""

from __future__ import annotations

import asyncio
import hashlib
import time

import httpx


class GeminiContextCache:
    def __init__(self, client: httpx.AsyncClient, *, ttl_seconds: int = 3600) -> None:
        self.client = client
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(model: str, text: str) -> str:
        return f"{model}:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"

    async def get_or_create(self, api_key: str, model: str, text: str, base_url: str) -> tuple[str | None, int]:
        """Return (cache_resource_name | None, cache_creation_input_tokens).

        The token count is non-zero only when a fresh entry is minted; a reused
        entry reports zero so the caller can bill it as a cache *read*.
        """
        key = self._key(model, text)
        now = time.time()
        async with self._lock:
            if key in self._store:
                name, expires = self._store[key]
                if expires > now + 5:
                    return name, 0
                self._store.pop(key, None)
        body = {"model": f"models/{model}", "contents": [{"role": "user", "parts": [{"text": text}]}], "ttl": f"{self.ttl}s"}
        try:
            response = await self.client.post(f"{base_url}/cachedContents?key={api_key}", json=body, timeout=60.0)
            if response.status_code != 200:
                return None, 0
            payload = response.json()
            name = payload.get("name")  # "cachedContents/<id>"
            if not name:
                return None, 0
            tokens = (payload.get("usageMetadata") or {}).get("totalTokenCount", 0) or len(text) // 4
        except (httpx.HTTPError, ValueError):
            return None, 0
        async with self._lock:
            self._store[key] = (name, now + self.ttl)
        return name, tokens
