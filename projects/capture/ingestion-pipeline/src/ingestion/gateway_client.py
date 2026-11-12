"""Ingestion's one client for the AI OS gateway. Nothing else imports httpx for model calls.

The gateway owns provider keys, profiles, budgets and the call log. This file
only knows its address, its three endpoints and the login token.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_URL = "http://127.0.0.1:8000"
EMBEDDING_PROFILE = "chunker-v1"


class GatewayError(RuntimeError):
    """The gateway answered with an error; the message keeps its status and detail."""


class LLM:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        timeout: float = 600,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        token = (token or os.environ.get("AI_OS_TOKEN", "")).strip()
        if not token:
            raise RuntimeError("AI_OS_TOKEN is not set; the gateway refuses calls without it")
        base_url = base_url or os.environ.get("AI_OS_GATEWAY_URL", "").strip() or DEFAULT_URL
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/api/llm",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._http.request(method, path, json=body)
        if response.is_error:
            raise GatewayError(f"gateway {method} {path} failed with {response.status_code}: {response.text}")
        result: dict[str, Any] = response.json()
        return result

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
    ) -> dict[str, Any]:
        body = {
            "prompt": prompt, "messages": messages, "system": system,
            "profile": profile, "provider": provider, "model": model,
            "max_tokens": max_tokens, "temperature": temperature,
            "response_format": response_format,
        }
        return self._call("POST", "/chat", {k: v for k, v in body.items() if v is not None})

    def embed(
        self,
        text: str,
        task_type: str = "retrieval_document",
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Embed with the gateway's pinned profile (local nomic-embed-text, 768 numbers).

        Ingestion passes ``provider="ollama"``; sent as-is, the gateway would use
        Ollama's chat model. The profile names the embedding model exactly.
        """
        if provider not in (None, "ollama"):
            raise ValueError(f"ingestion embeds only through ollama, not {provider!r}")
        return self._call("POST", "/embed", {"text": text, "task_type": task_type, "profile": EMBEDDING_PROFILE})

    def resolve_chat_profile(self, profile: str) -> dict[str, Any]:
        """Return the provider and model a chat profile is pinned to, or fail if unavailable."""
        return self._call("GET", f"/chat/profiles/{profile}")

    def close(self) -> None:
        self._http.close()
