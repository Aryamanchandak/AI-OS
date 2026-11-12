"""Small helpers shared by the independently-owned HTTP provider packages."""

from __future__ import annotations

from typing import Any

import httpx

from gateway.llm.providers.base import ProviderError


async def post_json(client: httpx.AsyncClient, url: str, *, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await client.post(url, headers=headers, json=payload, timeout=180.0)
    except httpx.TimeoutException as exc:
        raise ProviderError("provider request timed out", status=504, retryable=True) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(str(exc), status=502, retryable=True) from exc
    if response.is_error:
        message = response.text[:1000]
        raise ProviderError(message, status=response.status_code, retryable=response.status_code in {408, 409, 429} or response.status_code >= 500)
    value = response.json()
    if not isinstance(value, dict):
        raise ProviderError("provider returned a non-object response")
    return value
