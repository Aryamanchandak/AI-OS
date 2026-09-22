"""Google Gemini generateContent and embedding adapter."""

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
    as_dict, coerce_obj, flatten_system, iter_image_blocks, tool_specs,
)
from gateway.llm.providers.gemini.context_cache import GeminiContextCache
from gateway.llm.providers.gemini.schema import clean as clean_schema

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

#: `thinkingBudget` values for the models that take a budget rather than a level.
BUDGETS = {"low": 2048, "medium": 8192, "high": 24576}

#: Below this many characters a context cache costs more to mint than it saves.
MIN_CACHEABLE_CHARS = 1000


def thinking_knob(model: str) -> str | None:
    """Return 'level' for thinkingLevel-capable models, 'budget' for
    thinkingBudget-only models, or None when the model cannot think at all."""
    name = (model or "").lower()
    if "gemini" not in name or "flash-lite" in name:
        return None
    if "2.5-pro" in name or "3-pro" in name or "3.1-pro" in name:
        return "level"
    if "3-flash" in name or "3.1-flash" in name:
        return "level"  # 3.x flash (non-lite) supports thinkingLevel
    if "2.5-flash" in name:
        return "budget"
    return None


def supports_thinking(model: str) -> bool:
    return thinking_knob(model) is not None


class GeminiProvider:
    def __init__(self, name: str, api_key: str, model: str, client: httpx.AsyncClient,
                 *, context_cache: GeminiContextCache | None = None) -> None:
        self.name, self.api_key, self.model, self.client = name, api_key, model, client
        self.context_cache = context_cache or GeminiContextCache(client)
        # Reasoning is per-model: flash-lite has no thinking channel at all, so
        # advertising it would make `reasoning_applied` a lie on those pins.
        self.capabilities = ProviderCapabilities(
            vision=True, reasoning=supports_thinking(model), embeddings=True,
            max_context_tokens=1_000_000,
        )

    # ── request translation ────────────────────────────────────────────────

    @staticmethod
    def _parts(content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str):
            return [{"text": content}]
        if not isinstance(content, list):
            return [{"text": str(content)}]
        parts: list[dict[str, Any]] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append({"text": block.get("text", "")})
        parts.extend({"inlineData": {"mimeType": media, "data": data}} for media, data in iter_image_blocks(content))
        return parts

    def _contents(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "system":
                continue
            if role == "tool":
                contents.append({"role": "user", "parts": [{"functionResponse": {
                    "name": message.get("tool_name") or message.get("name") or "tool",
                    "response": coerce_obj(message.get("content")),
                }}]})
                continue
            if role == "assistant":
                parts: list[dict[str, Any]] = []
                if message.get("content"):
                    parts.extend(self._parts(message["content"]))
                for call in message.get("tool_calls") or []:
                    part: dict[str, Any] = {"functionCall": {"name": call["name"], "args": call.get("arguments") or {}}}
                    # Echo the thought signature back, or multi-turn tool use on a
                    # thinking model degrades: Gemini drops the reasoning context.
                    if signature := (call.get("provider_meta") or {}).get("thoughtSignature"):
                        part["thoughtSignature"] = signature
                    parts.append(part)
                contents.append({"role": "model", "parts": parts})
                continue
            contents.append({"role": "user", "parts": self._parts(message.get("content", ""))})
        return contents

    @staticmethod
    def _tools(tools: list[Any] | None) -> list[dict[str, Any]] | None:
        specs = tool_specs(tools)
        if not specs:
            return None
        return [{"functionDeclarations": [{
            "name": spec["name"], "description": spec.get("description", ""),
            "parameters": spec.get("input_schema") or {"type": "object", "properties": {}},
        } for spec in specs]}]

    async def _build_body(self, *, messages: list[dict[str, Any]], system: Any, model: str,
                          max_tokens: int, temperature: float, tools: list[Any] | None,
                          tool_choice: Any, response_format: Any, reasoning: str | None,
                          cache_system: bool) -> tuple[dict[str, Any], bool, int, int]:
        system_text, blocks, has_cache_marker = flatten_system(system)
        cacheable = None
        if cache_system or has_cache_marker:
            cacheable = "\n".join(b["text"] for b in blocks if b["cache"]) if has_cache_marker else system_text
        cache_name, cache_create_tokens, cache_read_tokens = None, 0, 0
        if cacheable and len(cacheable) > MIN_CACHEABLE_CHARS:
            cache_name, cache_create_tokens = await self.context_cache.get_or_create(self.api_key, model, cacheable, BASE_URL)
            if cache_name and cache_create_tokens == 0:
                cache_read_tokens = len(cacheable) // 4  # reused entry: bill as a read

        body: dict[str, Any] = {
            "contents": self._contents(messages),
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        if cache_name:
            body["cachedContent"] = cache_name
            # Strip the cached part from the system instruction, or it bills twice.
            remaining = "\n".join(b["text"] for b in blocks if not b["cache"]) if has_cache_marker else ""
            if remaining:
                body["systemInstruction"] = {"parts": [{"text": remaining}]}
        elif system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}

        if translated := self._tools(tools):
            body["tools"] = translated
            mode = "NONE" if tool_choice == "none" else ("ANY" if isinstance(tool_choice, dict) else "AUTO")
            body["toolConfig"] = {"function_calling_config": {"mode": mode}}

        if spec := as_dict(response_format):
            if schema := spec.get("schema"):
                body["generationConfig"]["responseMimeType"] = "application/json"
                body["generationConfig"]["responseSchema"] = clean_schema(schema)
            elif spec.get("type") == "json_object":
                body["generationConfig"]["responseMimeType"] = "application/json"

        reasoning_applied = False
        if reasoning and reasoning != "off":
            knob = thinking_knob(model)
            if knob == "level":
                body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": reasoning}
                reasoning_applied = True
            elif knob == "budget" and reasoning in BUDGETS:
                body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": BUDGETS[reasoning]}
                reasoning_applied = True
        return body, reasoning_applied, cache_create_tokens, cache_read_tokens

    # ── calls ──────────────────────────────────────────────────────────────

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None, model: str | None = None,
                   max_tokens: int = 2048, temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None, reasoning: str | None = None,
                   cache_system: bool = False) -> ProviderResult:
        selected = model or self.model
        body, reasoning_applied, cache_create_tokens, cache_read_tokens = await self._build_body(
            messages=messages, system=system, model=selected, max_tokens=max_tokens,
            temperature=temperature, tools=tools, tool_choice=tool_choice,
            response_format=response_format, reasoning=reasoning, cache_system=cache_system)
        url = f"{BASE_URL}/models/{selected}:generateContent?key={self.api_key}"

        try:
            response = await self.client.post(url, json=body, timeout=180.0)
            if response.status_code == 400:
                # A 400 is usually one of two optional knobs the model rejected.
                # Strip them and retry once rather than failing a whole call over
                # an accelerator the caller never asked for by name.
                if reasoning_applied:
                    body["generationConfig"].pop("thinkingConfig", None)
                    reasoning_applied = False
                if "cachedContent" in body and "cache" in response.text.lower():
                    body.pop("cachedContent", None)
                    if system_text := flatten_system(system)[0]:
                        body["systemInstruction"] = {"parts": [{"text": system_text}]}
                    cache_create_tokens = cache_read_tokens = 0
                response = await self.client.post(url, json=body, timeout=180.0)
        except httpx.TimeoutException as exc:
            raise ProviderError("gemini request timed out", status=504, retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"gemini transport error: {exc}", status=502, retryable=True) from exc

        if response.status_code != 200:
            raise ProviderError(f"gemini HTTP {response.status_code}: {response.text[:400]}",
                                status=response.status_code, retryable=response.status_code not in (400, 401))
        payload = response.json()
        candidates = payload.get("candidates") or []
        if not candidates:
            raise ProviderError(f"gemini no candidates: {json.dumps(payload)[:200]}", status=200, retryable=True)
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        text = "".join(part.get("text", "") for part in parts if "text" in part)
        calls: list[dict[str, Any]] = []
        for part in parts:
            function = part.get("functionCall") or part.get("function_call")
            if not function:
                continue
            call: dict[str, Any] = {"id": f"call_{uuid.uuid4().hex[:8]}", "name": function.get("name", ""),
                                    "arguments": function.get("args") or function.get("arguments") or {}}
            if signature := (part.get("thoughtSignature") or part.get("thought_signature")):
                call["provider_meta"] = {"thoughtSignature": signature}
            calls.append(call)

        usage = payload.get("usageMetadata") or {}
        cached = usage.get("cachedContentTokenCount", 0) or 0
        if cached and not cache_read_tokens:
            cache_read_tokens = cached
        stop = str(candidates[0].get("finishReason") or "STOP").upper()
        return ProviderResult(
            provider=self.name, model=selected, text=text, tool_calls=calls,
            stop_reason="tool_use" if calls else ("max_tokens" if stop == "MAX_TOKENS" else "end_turn"),
            usage=ProviderUsage(
                input_tokens=usage.get("promptTokenCount", 0) or 0,
                output_tokens=usage.get("candidatesTokenCount", 0) or 0,
                cache_creation_input_tokens=cache_create_tokens,
                cache_read_input_tokens=cache_read_tokens),
            raw=payload, tool_call_dialect="native" if tools else "none", reasoning_applied=reasoning_applied)

    def stream(self, **kwargs: Any) -> AsyncIterator[str]:
        # Gemini inherits the buffered fallback in the legacy tree too
        # (`BaseProvider.stream`); there is no incremental parser to preserve.
        return fallback_stream(self.chat, **kwargs)

    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]:
        selected = model or self.model
        try:
            response = await self.client.post(
                f"{BASE_URL}/models/{selected}:embedContent?key={self.api_key}",
                json={"model": f"models/{selected}", "content": {"parts": [{"text": text}]}, "taskType": task_type.upper()},
                timeout=180.0)
        except httpx.HTTPError as exc:
            raise ProviderError(f"gemini transport error: {exc}", status=502, retryable=True) from exc
        if response.status_code != 200:
            raise ProviderError(f"gemini HTTP {response.status_code}: {response.text[:400]}", status=response.status_code)
        return list((response.json().get("embedding") or {}).get("values") or [])
