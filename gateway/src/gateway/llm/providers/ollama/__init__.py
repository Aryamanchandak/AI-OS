"""Ollama adapter for local chat, vision, tools, and embeddings."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any
import uuid

import httpx

from gateway.llm.providers.base import ProviderCapabilities, ProviderResult, ProviderUsage, system_text
from gateway.llm.providers.http import post_json


class OllamaProvider:
    def __init__(self, name: str, model: str, client: httpx.AsyncClient,
                 base_url: str = "http://localhost:11434", *, vision: bool = False,
                 context_window: int = 32_000, needs_think_false: bool = False) -> None:
        self.name, self.model, self.client, self.base_url = name, model, client, base_url.rstrip("/")
        self.needs_think_false = needs_think_false
        self.capabilities = ProviderCapabilities(vision=vision, embeddings=True, max_context_tokens=context_window)

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None, model: str | None = None,
                   max_tokens: int = 2048, temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None, reasoning: str | None = None) -> ProviderResult:
        del tool_choice, reasoning
        selected = model or self.model
        translated = ([{"role": "system", "content": system_text(system)}] if system_text(system) else []) + messages
        body: dict[str, Any] = {"model": selected, "messages": translated, "options": {"temperature": temperature, "num_predict": max_tokens}, "stream": False}
        if self.needs_think_false: body["think"] = False
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": (x if isinstance(x, dict) else x.model_dump())["name"], "description": (x if isinstance(x, dict) else x.model_dump()).get("description", ""), "parameters": (x if isinstance(x, dict) else x.model_dump()).get("input_schema") or {"type": "object", "properties": {}}}} for x in tools]
        if response_format:
            spec = response_format if isinstance(response_format, dict) else response_format.model_dump(by_alias=True); body["format"] = spec.get("schema") or "json"
        payload = await post_json(self.client, f"{self.base_url}/api/chat", headers={"content-type": "application/json"}, payload=body)
        msg = payload.get("message") or {}; calls = []
        for raw in msg.get("tool_calls") or []:
            fn = raw.get("function") or {}; calls.append({"id": raw.get("id") or f"call_{uuid.uuid4().hex[:8]}", "name": fn.get("name", ""), "arguments": fn.get("arguments") or {}})
        return ProviderResult(provider=self.name, model=selected, text=msg.get("content", "") or "", tool_calls=calls,
            stop_reason="tool_use" if calls else ("max_tokens" if payload.get("done_reason") in {"length", "max_tokens"} else "end_turn"),
            usage=ProviderUsage(input_tokens=payload.get("prompt_eval_count", 0) or 0, output_tokens=payload.get("eval_count", 0) or 0), raw=payload,
            tool_call_dialect="native" if tools else "none")

    async def stream(self, **kwargs: Any) -> AsyncIterator[bytes]:
        result = await self.chat(**kwargs); yield b"data: " + json.dumps({"text": result.text}).encode() + b"\n\n"; yield b"data: [DONE]\n\n"

    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]:
        del task_type
        payload = await post_json(self.client, f"{self.base_url}/api/embed", headers={"content-type": "application/json"}, payload={"model": model or self.model, "input": text})
        values = payload.get("embeddings") or []
        return list(values[0] if values and isinstance(values[0], list) else payload.get("embedding") or [])
