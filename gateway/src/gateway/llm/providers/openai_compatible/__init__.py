"""OpenAI-compatible chat-completions adapter for custom endpoints."""

from __future__ import annotations

from typing import Any
import uuid

import httpx

from gateway.llm.providers.base import (
    ProviderCapabilities, ProviderError, ProviderResult, ProviderUsage,
    normalize_stop_reason, openai_messages,
)
from gateway.llm.providers.capabilities import model_supports_reasoning
from gateway.llm.providers.content import arguments, as_dict, flatten_system, tool_specs
from gateway.llm.providers.http import post_json


class OpenAICompatibleProvider:
    def __init__(self, name: str, api_key: str, model: str, base_url: str,
                 client: httpx.AsyncClient, *, vision: bool = False) -> None:
        self.name, self.api_key, self.model = name, api_key, model
        self.base_url, self.client = base_url.rstrip("/"), client
        self.capabilities = ProviderCapabilities(vision=vision, reasoning=model_supports_reasoning(model))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _tools(tools: list[Any] | None) -> list[dict[str, Any]] | None:
        specs = tool_specs(tools)
        if not specs:
            return None
        return [{"type": "function", "function": {
            "name": spec["name"], "description": spec.get("description", ""),
            "parameters": spec.get("input_schema") or {"type": "object", "properties": {}},
        }} for spec in specs]

    def _body(self, *, messages: list[dict[str, Any]], system: Any, model: str | None,
              max_tokens: int, temperature: float, tools: list[Any] | None, tool_choice: Any,
              response_format: Any, reasoning: str | None) -> tuple[dict[str, Any], bool]:
        selected = model or self.model
        body: dict[str, Any] = {
            "model": selected,
            "messages": openai_messages(messages, flatten_system(system)[0] or None),
            "max_tokens": max_tokens, "temperature": temperature, "stream": False,
        }
        if translated := self._tools(tools):
            body["tools"] = translated
            if tool_choice is not None:
                body["tool_choice"] = tool_choice if isinstance(tool_choice, (str, dict)) else "auto"
            else:
                body["tool_choice"] = "auto"
        if spec := as_dict(response_format):
            if schema := spec.get("schema"):
                body["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": spec.get("name", "out"), "schema": schema, "strict": spec.get("strict", True)}}
            elif spec.get("type") == "json_object":
                body["response_format"] = {"type": "json_object"}
        reasoning_applied = bool(reasoning and reasoning != "off")
        if reasoning_applied:
            body["reasoning_effort"] = reasoning
        return body, reasoning_applied

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None,
                   model: str | None = None, max_tokens: int = 2048,
                   temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None,
                   reasoning: str | None = None, cache_system: bool = False) -> ProviderResult:
        del cache_system  # no prompt-cache dial on this surface
        selected = model or self.model
        body, reasoning_applied = self._body(
            messages=messages, system=system, model=model, max_tokens=max_tokens,
            temperature=temperature, tools=tools, tool_choice=tool_choice,
            response_format=response_format, reasoning=reasoning)
        payload = await post_json(self.client, f"{self.base_url}/chat/completions",
                                  headers=self._headers(), payload=body)
        choices = payload.get("choices") or []
        if not choices:
            raise ProviderError(f"{self.name} returned no choices")
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        text = content if isinstance(content, str) else "".join(
            x.get("text", "") for x in content if isinstance(x, dict))
        calls = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") or {}
            calls.append({"id": raw.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                          "name": function.get("name", ""),
                          "arguments": arguments(function.get("arguments") or {})})
        usage = payload.get("usage") or {}
        return ProviderResult(
            provider=self.name, model=payload.get("model") or selected, text=text, tool_calls=calls,
            stop_reason="tool_use" if calls else normalize_stop_reason(choice.get("finish_reason")),
            usage=ProviderUsage(input_tokens=usage.get("prompt_tokens", 0) or 0,
                                output_tokens=usage.get("completion_tokens", 0) or 0,
                                cache_read_input_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0),
            raw=payload, tool_call_dialect="native" if tools else "none", reasoning_applied=reasoning_applied)


    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]:
        del task_type
        payload = await post_json(self.client, f"{self.base_url}/embeddings", headers=self._headers(),
                                  payload={"model": model or self.model, "input": text})
        return list((payload.get("data") or [{}])[0].get("embedding") or [])
