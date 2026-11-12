"""Anthropic Messages API adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
import uuid

import httpx

from gateway.llm.providers.anthropic.schema import clean as clean_schema
from gateway.llm.providers.base import (
    ProviderCapabilities, ProviderError, ProviderResult, ProviderUsage, fallback_stream,
)
from gateway.llm.providers.content import (
    as_dict, flatten_system, iter_image_blocks, text_of, tool_specs,
)

BASE_URL = "https://api.anthropic.com/v1"


class AnthropicProvider:
    capabilities = ProviderCapabilities(vision=True, reasoning=True)
    _THINKING = {"low": 1024, "medium": 5000, "high": 10000}

    def __init__(self, name: str, api_key: str, model: str, client: httpx.AsyncClient) -> None:
        self.name, self.api_key, self.model, self.client = name, api_key, model, client

    @staticmethod
    def _append(result: list[dict[str, Any]], role: str, blocks: list[dict[str, Any]]) -> None:
        """Append blocks, merging into the previous turn when the role repeats —
        Anthropic rejects consecutive messages from the same role."""
        if not blocks:
            return
        if result and result[-1]["role"] == role:
            result[-1]["content"].extend(blocks)
        else:
            result.append({"role": role, "content": blocks})

    def _messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for message in messages:
            role, content = message.get("role"), message.get("content")
            if role == "user":
                blocks: list[dict[str, Any]] = []
                if text := text_of(content):
                    blocks.append({"type": "text", "text": text})
                blocks.extend({"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}
                              for media, data in iter_image_blocks(content))
                self._append(result, "user", blocks)
            elif role == "assistant":
                blocks = [{"type": "text", "text": text_of(content)}] if text_of(content) else []
                blocks.extend({"type": "tool_use", "id": call["id"], "name": call["name"],
                               "input": call.get("arguments") or {}}
                              for call in message.get("tool_calls") or [])
                self._append(result, "assistant", blocks)
            elif role == "tool":
                # A tool result is a user-role block in the Messages dialect.
                self._append(result, "user", [{"type": "tool_result",
                                               "tool_use_id": message.get("tool_call_id") or "",
                                               "content": [{"type": "text", "text": text_of(content)}]}])
        return result

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None, model: str | None = None,
                   max_tokens: int = 2048, temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None, reasoning: str | None = None,
                   cache_system: bool = False) -> ProviderResult:
        selected = model or self.model
        system_text, blocks, has_cache = flatten_system(system)
        body: dict[str, Any] = {"model": selected, "messages": self._messages(messages),
                                "max_tokens": max_tokens, "temperature": temperature}
        if blocks and (cache_system or has_cache):
            # Per-block `cache_control` is what makes prompt caching real: without
            # it `cache_creation_input_tokens` is always 0 and a long, stable
            # system prompt is re-billed in full on every single turn.
            body["system"] = [{"type": "text", "text": block["text"],
                               **({"cache_control": {"type": "ephemeral"}} if block.get("cache") else {})}
                              for block in blocks]
        elif system_text:
            body["system"] = system_text

        if (specs := tool_specs(tools)) and tool_choice != "none":
            body["tools"] = [{"name": spec["name"], "description": spec.get("description", ""),
                              "input_schema": spec.get("input_schema") or {"type": "object", "properties": {}}}
                             for spec in specs]
            body["tool_choice"] = ({"type": "tool", "name": tool_choice["name"]}
                                   if isinstance(tool_choice, dict) and tool_choice.get("name")
                                   else {"type": tool_choice or "auto"})

        if spec := as_dict(response_format):
            schema = spec.get("schema")
            if not schema:
                raise ProviderError("anthropic structured output requires a JSON schema", status=400)
            body["output_config"] = {"format": {"type": "json_schema", "schema": clean_schema(schema)}}

        thinking = reasoning in self._THINKING
        if thinking:
            body["thinking"] = {"type": "enabled", "budget_tokens": self._THINKING[str(reasoning)]}

        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        try:
            response = await self.client.post(f"{BASE_URL}/messages", headers=headers, json=body, timeout=180.0)
            if response.status_code == 400 and thinking:
                # Retry once without the thinking budget: a model that does not
                # take the dial should not fail the call over it.
                body.pop("thinking", None)
                thinking = False
                response = await self.client.post(f"{BASE_URL}/messages", headers=headers, json=body, timeout=180.0)
        except httpx.TimeoutException as exc:
            raise ProviderError("anthropic request timed out", status=504, retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"anthropic transport error: {exc}", status=502, retryable=True) from exc

        if response.status_code != 200:
            raise ProviderError(f"anthropic HTTP {response.status_code}: {response.text[:400]}",
                                status=response.status_code,
                                retryable=response.status_code not in (400, 401, 403, 404))
        payload = response.json()
        content = payload.get("content") or []
        text = "".join(block.get("text", "") for block in content if block.get("type") == "text")
        calls = [{"id": block.get("id") or f"call_{uuid.uuid4().hex[:8]}", "name": block.get("name", ""),
                  "arguments": block.get("input") or {}}
                 for block in content if block.get("type") == "tool_use"]
        usage = payload.get("usage") or {}
        return ProviderResult(
            provider=self.name, model=payload.get("model") or selected, text=text, tool_calls=calls,
            stop_reason="tool_use" if calls else ("max_tokens" if payload.get("stop_reason") == "max_tokens" else "end_turn"),
            usage=ProviderUsage(input_tokens=usage.get("input_tokens", 0) or 0,
                                output_tokens=usage.get("output_tokens", 0) or 0,
                                cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0) or 0,
                                cache_read_input_tokens=usage.get("cache_read_input_tokens", 0) or 0),
            raw=payload, tool_call_dialect="native" if tools else "none", reasoning_applied=thinking)

    def stream(self, **kwargs: Any) -> AsyncIterator[str]:
        return fallback_stream(self.chat, **kwargs)

    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]:
        raise ProviderError("anthropic does not support embeddings", status=400)
