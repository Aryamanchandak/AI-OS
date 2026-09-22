"""Anthropic Messages API adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any
import uuid

import httpx

from gateway.llm.providers.base import ProviderCapabilities, ProviderError, ProviderResult, ProviderUsage, system_text
from gateway.llm.providers.http import post_json


class AnthropicProvider:
    capabilities = ProviderCapabilities(vision=True, reasoning=True)
    _THINKING = {"low": 1024, "medium": 5000, "high": 10000}

    def __init__(self, name: str, api_key: str, model: str, client: httpx.AsyncClient) -> None:
        self.name, self.api_key, self.model, self.client = name, api_key, model, client

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None, model: str | None = None,
                   max_tokens: int = 2048, temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None, reasoning: str | None = None) -> ProviderResult:
        selected = model or self.model
        body: dict[str, Any] = {"model": selected, "messages": [m for m in messages if m.get("role") != "system"], "max_tokens": max_tokens, "temperature": temperature}
        if value := system_text(system): body["system"] = value
        if tools and tool_choice != "none":
            body["tools"] = [{"name": (x if isinstance(x, dict) else x.model_dump())["name"], "description": (x if isinstance(x, dict) else x.model_dump()).get("description", ""), "input_schema": (x if isinstance(x, dict) else x.model_dump()).get("input_schema") or {"type": "object", "properties": {}}} for x in tools]
        if response_format:
            spec = response_format if isinstance(response_format, dict) else response_format.model_dump(by_alias=True)
            if not spec.get("schema"): raise ProviderError("anthropic structured output requires a JSON schema", status=400)
            body["output_config"] = {"format": {"type": "json_schema", "schema": spec["schema"]}}
        thinking = reasoning in self._THINKING
        if thinking: body["thinking"] = {"type": "enabled", "budget_tokens": self._THINKING[str(reasoning)]}
        payload = await post_json(self.client, "https://api.anthropic.com/v1/messages", headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, payload=body)
        content = payload.get("content") or []
        text = "".join(x.get("text", "") for x in content if x.get("type") == "text")
        calls = [{"id": x.get("id") or f"call_{uuid.uuid4().hex[:8]}", "name": x.get("name", ""), "arguments": x.get("input") or {}} for x in content if x.get("type") == "tool_use"]
        usage = payload.get("usage") or {}
        return ProviderResult(provider=self.name, model=payload.get("model") or selected, text=text, tool_calls=calls,
            stop_reason="tool_use" if calls else ("max_tokens" if payload.get("stop_reason") == "max_tokens" else "end_turn"),
            usage=ProviderUsage(input_tokens=usage.get("input_tokens", 0) or 0, output_tokens=usage.get("output_tokens", 0) or 0,
                cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0) or 0, cache_read_input_tokens=usage.get("cache_read_input_tokens", 0) or 0),
            raw=payload, tool_call_dialect="native" if tools else "none", reasoning_applied=thinking)

    async def stream(self, **kwargs: Any) -> AsyncIterator[bytes]:
        result = await self.chat(**kwargs); yield b"data: " + json.dumps({"text": result.text}).encode() + b"\n\n"; yield b"data: [DONE]\n\n"

    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]:
        raise ProviderError("anthropic does not support embeddings", status=400)
