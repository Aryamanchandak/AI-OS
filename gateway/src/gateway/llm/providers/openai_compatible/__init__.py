"""OpenAI-compatible chat-completions adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any
import uuid

import httpx

from gateway.llm.providers.base import ProviderCapabilities, ProviderResult, ProviderUsage, normalize_stop_reason, openai_messages
from gateway.llm.providers.http import post_json


class OpenAICompatibleProvider:
    capabilities = ProviderCapabilities(vision=False, reasoning=True)

    def __init__(self, name: str, api_key: str, model: str, base_url: str,
                 client: httpx.AsyncClient, *, vision: bool = False) -> None:
        self.name, self.api_key, self.model = name, api_key, model
        self.base_url, self.client = base_url.rstrip("/"), client
        self.capabilities = ProviderCapabilities(vision=vision, reasoning=True)

    @staticmethod
    def _tools(tools: list[Any] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        values = []
        for tool in tools:
            item = tool if isinstance(tool, dict) else tool.model_dump()
            values.append({"type": "function", "function": {"name": item["name"], "description": item.get("description", ""), "parameters": item.get("input_schema") or {"type": "object", "properties": {}}}})
        return values

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None,
                   model: str | None = None, max_tokens: int = 2048,
                   temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None,
                   reasoning: str | None = None) -> ProviderResult:
        selected = model or self.model
        body: dict[str, Any] = {"model": selected, "messages": openai_messages(messages, system), "max_tokens": max_tokens, "temperature": temperature, "stream": False}
        if translated := self._tools(tools):
            body["tools"] = translated
            body["tool_choice"] = tool_choice or "auto"
        if response_format:
            spec = response_format if isinstance(response_format, dict) else response_format.model_dump(by_alias=True)
            if spec.get("schema"):
                body["response_format"] = {"type": "json_schema", "json_schema": {"name": spec.get("name", "out"), "schema": spec["schema"], "strict": spec.get("strict", True)}}
            elif spec.get("type") == "json_object":
                body["response_format"] = {"type": "json_object"}
        reasoning_applied = bool(reasoning and reasoning != "off")
        if reasoning_applied:
            body["reasoning_effort"] = reasoning
        payload = await post_json(self.client, f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, payload=body)
        choices = payload.get("choices") or []
        if not choices:
            from gateway.llm.providers.base import ProviderError
            raise ProviderError(f"{self.name} returned no choices")
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        text = content if isinstance(content, str) else "".join(x.get("text", "") for x in content if isinstance(x, dict))
        calls = []
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try: args = json.loads(args)
                except json.JSONDecodeError: args = {"_raw": args}
            calls.append({"id": raw.get("id") or f"call_{uuid.uuid4().hex[:8]}", "name": fn.get("name", ""), "arguments": args})
        usage = payload.get("usage") or {}
        return ProviderResult(provider=self.name, model=payload.get("model") or selected, text=text, tool_calls=calls,
            stop_reason="tool_use" if calls else normalize_stop_reason(choice.get("finish_reason")),
            usage=ProviderUsage(input_tokens=usage.get("prompt_tokens", 0) or 0, output_tokens=usage.get("completion_tokens", 0) or 0,
                cache_read_input_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0),
            raw=payload, tool_call_dialect="native" if tools else "none", reasoning_applied=reasoning_applied)

    async def stream(self, **kwargs: Any) -> AsyncIterator[bytes]:
        result = await self.chat(**kwargs)
        yield b"data: " + json.dumps({"text": result.text}).encode() + b"\n\n"
        yield b"data: [DONE]\n\n"

    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]:
        del task_type
        payload = await post_json(self.client, f"{self.base_url}/embeddings", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, payload={"model": model or self.model, "input": text})
        return list((payload.get("data") or [{}])[0].get("embedding") or [])
