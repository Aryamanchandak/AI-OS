"""Ollama adapter for local chat, vision, tools, and embeddings."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any
import uuid

import httpx

from gateway.llm.providers.base import (
    ProviderCapabilities, ProviderResult, ProviderUsage, fallback_stream,
)
from gateway.llm.providers.content import (
    arguments, as_dict, extract_text_blocks, flatten_system, iter_image_blocks, tool_specs,
)
from gateway.llm.providers.http import post_json
from gateway.llm.providers.ollama.tools import (
    parse_prompted_call, prompted_system, supports_native_tools,
)


class OllamaProvider:
    def __init__(self, name: str, model: str, client: httpx.AsyncClient,
                 base_url: str = "http://localhost:11434", *, vision: bool = False,
                 context_window: int = 32_000, needs_think_false: bool = False) -> None:
        self.name, self.model, self.client, self.base_url = name, model, client, base_url.rstrip("/")
        self.needs_think_false = needs_think_false
        # `tools` is unconditionally True: a model without a native tool API
        # still gets the prompted fallback below, so tool calling never vanishes.
        self.capabilities = ProviderCapabilities(
            vision=vision, tools=True, reasoning=False, embeddings=True,
            max_context_tokens=context_window)

    def _translate(self, messages: list[dict[str, Any]], system_text: str,
                   *, prompted_fallback: bool = False) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if system_text:
            out.append({"role": "system", "content": system_text})
        for message in messages:
            role, content = message.get("role"), message.get("content")
            if role == "system":
                if not system_text:
                    out.append({"role": "system", "content": content})
                continue
            if role == "tool":
                if prompted_fallback:
                    # No tool role exists in the prompted dialect — fold the
                    # result into the next user turn so the model still sees it.
                    out.append({"role": "user", "content": f'tool_result {{"id":"{message.get("tool_call_id", "")}","output":{json.dumps(content if isinstance(content, str) else json.dumps(content))}}}'})
                else:
                    out.append({"role": "tool", "content": content if isinstance(content, str) else json.dumps(content)})
                continue
            if role == "assistant" and message.get("tool_calls"):
                calls = [{"function": {"name": call["name"], "arguments": call.get("arguments") or {}}}
                         for call in message["tool_calls"]]
                value = extract_text_blocks(content) if isinstance(content, list) else (content or "")
                out.append({"role": "assistant", "content": value, "tool_calls": calls})
                continue
            if isinstance(content, list):
                # Ollama's vision dialect: text stays in `content`, images move
                # to a sibling `images` array of bare base64 strings.
                entry: dict[str, Any] = {"role": role, "content": extract_text_blocks(content)}
                if images := [data for _, data in iter_image_blocks(content)]:
                    entry["images"] = images
                out.append(entry)
            else:
                out.append({"role": role, "content": content})
        return out

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None, model: str | None = None,
                   max_tokens: int = 2048, temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None, reasoning: str | None = None,
                   cache_system: bool = False) -> ProviderResult:
        del tool_choice, reasoning, cache_system  # Ollama exposes no dial for these
        selected = model or self.model
        system_text = flatten_system(system)[0]
        native = bool(tools) and supports_native_tools(selected)
        prompted_fallback = bool(tools) and not native
        if prompted_fallback:
            system_text = (system_text + "\n\n" if system_text else "") + prompted_system(tools or [])

        body: dict[str, Any] = {
            "model": selected,
            "messages": self._translate(messages, system_text, prompted_fallback=prompted_fallback),
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": False,
        }
        if self.needs_think_false:
            body["think"] = False
        if native:
            body["tools"] = [{"type": "function", "function": {
                "name": spec["name"], "description": spec.get("description", ""),
                "parameters": spec.get("input_schema") or {"type": "object", "properties": {}},
            }} for spec in tool_specs(tools)]
        if spec := as_dict(response_format):
            if schema := spec.get("schema"):
                body["format"] = schema
            elif spec.get("type") == "json_object":
                body["format"] = "json"

        payload = await post_json(self.client, f"{self.base_url}/api/chat",
                                  headers={"content-type": "application/json"}, payload=body)
        message = payload.get("message") or {}
        text = message.get("content", "") or ""
        calls: list[dict[str, Any]] = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") or {}
            calls.append({"id": raw.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                          "name": function.get("name", ""),
                          "arguments": arguments(function.get("arguments") or {})})

        dialect = "native" if native else ("prompted_fallback" if prompted_fallback else "none")
        if prompted_fallback and not calls and (parsed := parse_prompted_call(text)):
            calls, text = [parsed], ""

        return ProviderResult(
            provider=self.name, model=selected, text=text, tool_calls=calls,
            stop_reason="tool_use" if calls else ("max_tokens" if payload.get("done_reason") in {"length", "max_tokens"} else "end_turn"),
            usage=ProviderUsage(input_tokens=payload.get("prompt_eval_count", 0) or 0,
                                output_tokens=payload.get("eval_count", 0) or 0),
            raw=payload, tool_call_dialect=dialect)

    def stream(self, **kwargs: Any) -> AsyncIterator[str]:
        return fallback_stream(self.chat, **kwargs)

    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]:
        del task_type
        payload = await post_json(self.client, f"{self.base_url}/api/embed",
                                  headers={"content-type": "application/json"},
                                  payload={"model": model or self.model, "input": text})
        values = payload.get("embeddings") or []
        return list(values[0] if values and isinstance(values[0], list) else payload.get("embedding") or [])
