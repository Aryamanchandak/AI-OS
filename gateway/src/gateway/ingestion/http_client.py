"""Synchronous, profile based HTTP access to Gateway's LLM routes."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx

from gateway.platform.service_registry import gateway_address

_gateway_url: str | None = None


def configure_gateway_url(url: str | None) -> None:
    """Use the address resolved by Gateway's lifespan registry."""
    global _gateway_url
    _gateway_url = url


class GatewayHTTPError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail[:500]
        super().__init__(f"Gateway HTTP {status_code}: {self.detail}")


class GatewayHTTPClient:
    """One reusable client object; each request uses a short lived connection."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 600,
        client: httpx.Client | None = None,
    ) -> None:
        resolved_url = base_url or _gateway_url or gateway_address().url
        self.base_url = resolved_url.rstrip("/")
        self.timeout = timeout
        self._client = client

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        token = os.environ.get("AI_OS_TOKEN", "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if self._client is None:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, self.base_url + path, json=body, headers=headers)
        else:
            response = self._client.request(method, self.base_url + path, json=body, headers=headers)
        if not response.is_success:
            try:
                payload = response.json()
                detail = payload.get("detail") or payload.get("error") or payload
            except (ValueError, AttributeError):
                detail = response.text
            raise GatewayHTTPError(response.status_code, str(detail).replace("\n", " "))
        return dict(response.json())

    def chat(
        self,
        prompt: str | None = None,
        *,
        messages: list[dict[str, Any]] | None = None,
        system: Any = None,
        profile: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        response_format: Any = None,
        **options: Any,
    ) -> dict[str, Any]:
        body = {
            "prompt": prompt, "messages": messages, "system": system,
            "profile": profile, "provider": provider, "model": model,
            "max_tokens": max_tokens, "temperature": temperature,
            "response_format": response_format, **options,
        }
        return self._request("POST", "/api/llm/chat", {key: value for key, value in body.items() if value is not None})

    def embed(
        self,
        text: str,
        task_type: str = "retrieval_document",
        profile: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        body = {"text": text, "task_type": task_type, "profile": profile, "provider": provider, "model": model}
        return self._request("POST", "/api/llm/embed", {key: value for key, value in body.items() if value is not None})

    def resolve_chat_profile(self, profile: str) -> dict[str, Any]:
        return self._request("GET", f"/api/llm/chat/profiles/{quote(profile, safe='')}")
