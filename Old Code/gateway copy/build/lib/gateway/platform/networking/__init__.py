"""Lifespan-owned outbound HTTP client."""

from __future__ import annotations

import httpx


class OutboundHTTPClient:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=False)

    async def close(self) -> None:
        await self.client.aclose()
