"""Native OpenAI adapter.

Deliberately *not* a subclass of `OpenAICompatibleProvider`. The dialects have
diverged: OpenAI's current models take `max_completion_tokens` (they reject
`max_tokens`), accept `parallel_tool_calls`, use an object form for a forced
tool choice, and gate `reasoning_effort` on the model family rather than on the
caller merely asking for it. Inheriting the compatible adapter silently sent all
four wrong. Ported from `glc_v5/glc/direct_providers.py:106`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any
import uuid

import httpx

from gateway.llm.providers.base import (
    ProviderCapabilities, ProviderError, ProviderResult, ProviderUsage, fallback_stream,
)
from gateway.llm.providers.content import (
    arguments, as_dict, extract_text_blocks, flatten_system, iter_image_blocks, text_of, tool_specs,
)

BASE_URL = "https://api.openai.com/v1"

#: Families that accept `reasoning_effort`. Sending it to anything else is a 400.
REASONING_FAMILIES = ("o1", "o3", "o4", "gpt-5")


class OpenAIProvider:
    capabilities = ProviderCapabilities(vision=True, reasoning=True)

    def __init__(self, name: str, api_key: str, model: str, client: httpx.AsyncClient) -> None:
        self.name, self.api_key, self.model, self.client = name, api_key, model, client

    def _messages(self, messages: list[dict[str, Any]], system: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if system:
            result.append({"role": "system", "content": system})
        for message in messages:
            role, content = message.get("role"), message.get("content")
            if role == "system":
                continue
            if role == "tool":
                result.append({"role": "tool", "tool_call_id": message.get("tool_call_id") or "",
                               "content": text_of(content)})
            elif role == "assistant" and message.get("tool_calls"):
                calls = [{"id": call["id"], "type": "function",
                          "function": {"name": call["name"], "arguments": json.dumps(call.get("arguments") or {})}}
                         for call in message["tool_calls"]]
                result.append({"role": role, "content": text_of(content) or None, "tool_calls": calls})
            elif isinstance(content, list):
                blocks: list[dict[str, Any]] = []
                if text := extract_text_blocks(content):
                    blocks.append({"type": "text", "text": text})
                blocks.extend({"type": "image_url", "image_url": {"url": f"data:{media};base64,{data}"}}
                              for media, data in iter_image_blocks(content))
                result.append({"role": role, "content": blocks})
            else:
                result.append({"role": role, "content": text_of(content)})
        return result

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None, model: str | None = None,
                   max_tokens: int = 2048, temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None, reasoning: str | None = None,
                   cache_system: bool = False) -> ProviderResult:
        del cache_system  # OpenAI caches automatically; there is no dial to set
        selected = model or self.model
        body: dict[str, Any] = {
            "model": selected,
            "messages": self._messages(messages, flatten_system(system)[0]),
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
        }
        if specs := tool_specs(tools):
            body["tools"] = [{"type": "function", "function": {
                "name": spec["name"], "description": spec.get("description", ""),
                "parameters": spec.get("input_schema") or {"type": "object", "properties": {}},
            }} for spec in specs]
            body["parallel_tool_calls"] = True
            body["tool_choice"] = ({"type": "function", "function": {"name": tool_choice["name"]}}
                                   if isinstance(tool_choice, dict) and tool_choice.get("name")
                                   else tool_choice or "auto")
        if spec := as_dict(response_format):
            if schema := spec.get("schema"):
                body["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": spec.get("name", "out"), "schema": schema, "strict": spec.get("strict", True)}}
            elif spec.get("type") == "json_object":
                body["response_format"] = {"type": "json_object"}

        reasoning_applied = bool(reasoning and reasoning != "off"
                                 and selected.lower().startswith(REASONING_FAMILIES))
        if reasoning_applied:
            body["reasoning_effort"] = reasoning

        headers = {"authorization": f"Bearer {self.api_key}", "content-type": "application/json"}
        try:
            response = await self.client.post(f"{BASE_URL}/chat/completions", headers=headers, json=body, timeout=180.0)
        except httpx.TimeoutException as exc:
            raise ProviderError("openai request timed out", status=504, retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai transport error: {exc}", status=502, retryable=True) from exc
        if response.status_code != 200:
            raise ProviderError(f"openai HTTP {response.status_code}: {response.text[:400]}",
                                status=response.status_code,
                                retryable=response.status_code not in (400, 401, 403, 404))
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ProviderError("openai returned no choices", status=200)
        message = choices[0].get("message") or {}
        content = message.get("content")
        text = content if isinstance(content, str) else extract_text_blocks(content or [])
        calls = [{"id": call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                  "name": (call.get("function") or {}).get("name", ""),
                  "arguments": arguments((call.get("function") or {}).get("arguments") or {})}
                 for call in message.get("tool_calls") or []]
        usage = payload.get("usage") or {}
        return ProviderResult(
            provider=self.name, model=payload.get("model") or selected, text=text, tool_calls=calls,
            stop_reason="tool_use" if calls else ("max_tokens" if choices[0].get("finish_reason") == "length" else "end_turn"),
            usage=ProviderUsage(input_tokens=usage.get("prompt_tokens", 0) or 0,
                                output_tokens=usage.get("completion_tokens", 0) or 0,
                                cache_read_input_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0),
            raw=payload, tool_call_dialect="native" if tools else "none", reasoning_applied=reasoning_applied)

    def stream(self, **kwargs: Any) -> AsyncIterator[str]:
        # The legacy direct adapter inherits `BaseProvider.stream`, i.e. one
        # buffered frame. Streaming incrementally here would silently change the
        # wire contract for `openai-*` while claiming to fix streaming.
        return fallback_stream(self.chat, **kwargs)

    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]:
        del task_type
        headers = {"authorization": f"Bearer {self.api_key}", "content-type": "application/json"}
        try:
            response = await self.client.post(f"{BASE_URL}/embeddings", headers=headers,
                                              json={"model": model or self.model, "input": text}, timeout=180.0)
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai transport error: {exc}", status=502, retryable=True) from exc
        if response.status_code != 200:
            raise ProviderError(f"openai HTTP {response.status_code}: {response.text[:400]}", status=response.status_code)
        return list((response.json().get("data") or [{}])[0].get("embedding") or [])
