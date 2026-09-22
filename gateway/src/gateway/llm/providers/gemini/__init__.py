"""Google Gemini generateContent and embedding adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any
import uuid

import httpx

from gateway.llm.providers.base import ProviderCapabilities, ProviderError, ProviderResult, ProviderUsage, system_text
from gateway.llm.providers.http import post_json


class GeminiProvider:
    capabilities = ProviderCapabilities(vision=True, reasoning=True, embeddings=True, max_context_tokens=1_000_000)

    def __init__(self, name: str, api_key: str, model: str, client: httpx.AsyncClient) -> None:
        self.name, self.api_key, self.model, self.client = name, api_key, model, client

    @staticmethod
    def _parts(content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str): return [{"text": content}]
        if not isinstance(content, list): return [{"text": str(content)}]
        parts = []
        for block in content:
            if not isinstance(block, dict): continue
            if block.get("type") == "text": parts.append({"text": block.get("text", "")})
            elif block.get("type") in {"image", "image_url"}:
                source = block.get("source") or block.get("image_url") or {}
                url = source.get("url", "") if isinstance(source, dict) else ""
                if url.startswith("data:") and ";base64," in url:
                    meta, data = url.split(",", 1); parts.append({"inlineData": {"mimeType": meta[5:].split(";")[0], "data": data}})
        return parts

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None, model: str | None = None,
                   max_tokens: int = 2048, temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None, reasoning: str | None = None) -> ProviderResult:
        del tool_choice
        selected = model or self.model
        body: dict[str, Any] = {"contents": [{"role": "model" if m.get("role") == "assistant" else "user", "parts": self._parts(m.get("content", ""))} for m in messages if m.get("role") != "system"], "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}}
        if value := system_text(system): body["systemInstruction"] = {"parts": [{"text": value}]}
        if tools:
            body["tools"] = [{"functionDeclarations": [{"name": (x if isinstance(x, dict) else x.model_dump())["name"], "description": (x if isinstance(x, dict) else x.model_dump()).get("description", ""), "parameters": (x if isinstance(x, dict) else x.model_dump()).get("input_schema") or {"type": "object", "properties": {}}} for x in tools]}]
        if response_format:
            spec = response_format if isinstance(response_format, dict) else response_format.model_dump(by_alias=True)
            body["generationConfig"]["responseMimeType"] = "application/json"
            if spec.get("schema"): body["generationConfig"]["responseSchema"] = spec["schema"]
        reasoning_applied = bool(reasoning and reasoning != "off" and "lite" not in selected)
        payload = await post_json(self.client, f"https://generativelanguage.googleapis.com/v1beta/models/{selected}:generateContent?key={self.api_key}", headers={"content-type": "application/json"}, payload=body)
        candidates = payload.get("candidates") or []
        if not candidates: raise ProviderError("gemini returned no candidates")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        text = "".join(x.get("text", "") for x in parts)
        calls = [{"id": f"call_{uuid.uuid4().hex[:8]}", "name": x["functionCall"].get("name", ""), "arguments": x["functionCall"].get("args") or {}} for x in parts if x.get("functionCall")]
        usage = payload.get("usageMetadata") or {}
        return ProviderResult(provider=self.name, model=selected, text=text, tool_calls=calls,
            stop_reason="tool_use" if calls else ("max_tokens" if candidates[0].get("finishReason") == "MAX_TOKENS" else "end_turn"),
            usage=ProviderUsage(input_tokens=usage.get("promptTokenCount", 0) or 0, output_tokens=usage.get("candidatesTokenCount", 0) or 0, cache_read_input_tokens=usage.get("cachedContentTokenCount", 0) or 0), raw=payload,
            tool_call_dialect="native" if tools else "none", reasoning_applied=reasoning_applied)

    async def stream(self, **kwargs: Any) -> AsyncIterator[bytes]:
        result = await self.chat(**kwargs); yield b"data: " + json.dumps({"text": result.text}).encode() + b"\n\n"; yield b"data: [DONE]\n\n"

    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]:
        selected = model or self.model
        payload = await post_json(self.client, f"https://generativelanguage.googleapis.com/v1beta/models/{selected}:embedContent?key={self.api_key}", headers={"content-type": "application/json"}, payload={"model": f"models/{selected}", "content": {"parts": [{"text": text}]}, "taskType": task_type.upper()})
        return list((payload.get("embedding") or {}).get("values") or [])
