"""Provider adapters for llm_gatewayV7.

Providers: Gemini tiers, OpenAI tiers, Anthropic tiers, and Ollama.

Each provider implements:
  async chat(messages, *, max_tokens, temperature, model, tools, tool_choice,
             reasoning, response_format, system_blocks) -> dict

The returned dict is normalised:
  {
    "text": str,
    "tool_calls": [ {"id","name","arguments"} ],
    "input_tokens": int, "output_tokens": int,
    "cache_creation_input_tokens": int, "cache_read_input_tokens": int,
    "stop_reason": "tool_use"|"end_turn"|"max_tokens",
    "model": str,
    "tool_call_dialect": "native"|"prompted_fallback"|"none",
    "reasoning_applied": bool,
  }
"""
from __future__ import annotations
import os, json, uuid, re
from typing import AsyncIterator, Optional, Any
import httpx


class ProviderError(Exception):
    def __init__(self, msg, status=None, retryable=True):
        super().__init__(msg)
        self.status = status
        self.retryable = retryable


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _flatten_system(system_blocks) -> tuple[str, list[dict], bool]:
    """Returns (joined_text, raw_blocks, has_cache_marker)."""
    if system_blocks is None:
        return "", [], False
    if isinstance(system_blocks, str):
        return system_blocks, [{"text": system_blocks, "cache": False}], False
    blocks = []
    has_cache = False
    parts = []
    for b in system_blocks:
        if isinstance(b, dict):
            t = b.get("text", "")
            c = bool(b.get("cache", False))
        else:
            t = getattr(b, "text", "")
            c = bool(getattr(b, "cache", False))
        blocks.append({"text": t, "cache": c})
        parts.append(t)
        if c:
            has_cache = True
    return "\n".join(parts), blocks, has_cache


def _empty_result(model: str) -> dict:
    return {
        "text": "", "tool_calls": [],
        "input_tokens": 0, "output_tokens": 0,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        "stop_reason": "end_turn", "model": model,
        "tool_call_dialect": "none", "reasoning_applied": False,
    }


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content)


def _split_content_blocks(content: Any) -> tuple[list[str], list[dict]]:
    """Split canonical message content into text and base64 image parts."""
    if not isinstance(content, list):
        return [], []
    text_parts: list[str] = []
    image_parts: list[dict] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text_parts.append(str(block.get("text", "")))
        elif block.get("type") == "image":
            image_parts.append(block)
    return text_parts, image_parts


def _json_loads_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {"_raw": value}


def _response_format_dict(response_format: Any) -> dict | None:
    if not response_format:
        return None
    if isinstance(response_format, dict):
        return response_format
    if hasattr(response_format, "model_dump"):
        return response_format.model_dump(by_alias=True)
    return None


_ANTHROPIC_SCHEMA_CONSTRAINTS = {
    "minimum": "Must be greater than or equal to {value}.",
    "maximum": "Must be less than or equal to {value}.",
    "exclusiveMinimum": "Must be greater than {value}.",
    "exclusiveMaximum": "Must be less than {value}.",
    "multipleOf": "Must be a multiple of {value}.",
    "minLength": "String length must be at least {value}.",
    "maxLength": "String length must be at most {value}.",
    "minItems": "Array must contain at least {value} item(s).",
    "maxItems": "Array must contain at most {value} item(s).",
    "minProperties": "Object must contain at least {value} properties.",
    "maxProperties": "Object must contain at most {value} properties.",
}
_ANTHROPIC_SCHEMA_ANNOTATIONS_TO_DROP = {
    "$schema",
    "default",
    "deprecated",
    "examples",
    "readOnly",
    "writeOnly",
}


def _anthropic_clean_schema(schema: dict) -> dict:
    """Return an Anthropic-compatible copy while preserving full validation.

    Anthropic's constrained decoder supports a useful JSON Schema subset. Its
    SDKs remove unsupported constraints, carry them into descriptions, and
    validate the response against the original schema afterwards. This raw
    HTTP adapter mirrors that contract; main.py remains the authoritative
    validator of the unmodified caller schema.
    """

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node

        cleaned: dict[str, Any] = {}
        constraint_notes: list[str] = []
        for key, value in node.items():
            template = _ANTHROPIC_SCHEMA_CONSTRAINTS.get(key)
            if template is not None:
                constraint_notes.append(template.format(value=value))
                continue
            if key in _ANTHROPIC_SCHEMA_ANNOTATIONS_TO_DROP:
                continue
            if key == "format":
                constraint_notes.append(f"Expected string format: {value}.")
                continue
            cleaned[key] = walk(value)

        if cleaned.get("type") == "object" or "properties" in cleaned:
            cleaned["additionalProperties"] = False

        if constraint_notes:
            description = str(cleaned.get("description") or "").strip()
            notes = " ".join(constraint_notes)
            cleaned["description"] = f"{description} {notes}".strip()
        return cleaned

    return walk(schema)


# ────────────────────────────────────────────────────────────────────────────
# Base
# ────────────────────────────────────────────────────────────────────────────

class BaseProvider:
    name: str = ""

    def __init__(self, api_key: str, model: str, base_url: str = ""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def chat(self, messages, *, max_tokens=2048, temperature=0.7, model=None,
                   tools=None, tool_choice=None, reasoning=None, response_format=None,
                   system_blocks=None, cache_system=False) -> dict:
        raise NotImplementedError

    async def stream(self, messages, *, max_tokens=2048, temperature=0.7, model=None,
                     tools=None, tool_choice=None, reasoning=None, response_format=None,
                     system_blocks=None, cache_system=False) -> AsyncIterator[str]:
        result = await self.chat(messages, max_tokens=max_tokens, temperature=temperature,
                                 model=model, tools=tools, tool_choice=tool_choice,
                                 reasoning=reasoning, response_format=response_format,
                                 system_blocks=system_blocks, cache_system=cache_system)
        if result["text"]:
            yield result["text"]


# ────────────────────────────────────────────────────────────────────────────
# OpenAI
# ────────────────────────────────────────────────────────────────────────────

_OPENAI_REASONING_MODELS = ("o",)


class OpenAIProvider(BaseProvider):
    name = "openai"
    capabilities = {
        "tools": True, "caching": False, "reasoning": True,
        "structured": True, "parallel_tools": True, "images": True,
    }

    def __init__(self, api_key: str, model: str):
        super().__init__(api_key, model, "https://api.openai.com/v1")

    def _translate_messages(self, messages, system_text: str) -> list[dict]:
        out: list[dict] = []
        if system_text:
            out.append({"role": "system", "content": system_text})
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": m.get("tool_call_id") or "",
                    "content": _message_text(m.get("content")),
                })
                continue
            if role == "assistant" and m.get("tool_calls"):
                tool_calls = []
                for tc in m["tool_calls"]:
                    tool_calls.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc.get("arguments") or {}),
                        },
                    })
                out.append({
                    "role": "assistant",
                    "content": _message_text(m.get("content")) or None,
                    "tool_calls": tool_calls,
                })
                continue
            content = m.get("content")
            if isinstance(content, list):
                text_parts, image_parts = _split_content_blocks(content)
                translated_content = [
                    {"type": "text", "text": text} for text in text_parts
                ]
                translated_content.extend({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image['media_type']};base64,{image['data']}"
                    },
                } for image in image_parts)
                out.append({"role": role, "content": translated_content})
            else:
                out.append({"role": role, "content": _message_text(content)})
        return out

    def _translate_tools(self, tools) -> list[dict] | None:
        if not tools:
            return None
        out = []
        for t in tools:
            d = t if isinstance(t, dict) else t.model_dump()
            out.append({
                "type": "function",
                "function": {
                    "name": d["name"],
                    "description": d.get("description", ""),
                    "parameters": d.get("input_schema") or {"type": "object", "properties": {}},
                },
            })
        return out

    def _translate_tool_choice(self, tool_choice: Any) -> Any:
        if tool_choice in (None, "auto"):
            return "auto"
        if tool_choice == "none":
            return "none"
        if isinstance(tool_choice, dict) and tool_choice.get("name"):
            return {"type": "function", "function": {"name": tool_choice["name"]}}
        return tool_choice

    @staticmethod
    def _supports_reasoning(model: str) -> bool:
        return model.lower().startswith(_OPENAI_REASONING_MODELS)

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                    parts.append(item.get("text", ""))
            return "".join(parts)
        return ""

    async def chat(self, messages, *, max_tokens=2048, temperature=0.7, model=None,
                   tools=None, tool_choice=None, reasoning=None, response_format=None,
                   system_blocks=None, cache_system=False):
        del cache_system
        m = model or self.model
        system_text, _, _ = _flatten_system(system_blocks)
        body: dict[str, Any] = {
            "model": m,
            "messages": self._translate_messages(messages, system_text),
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }

        translated_tools = self._translate_tools(tools)
        if translated_tools:
            body["tools"] = translated_tools
            body["parallel_tool_calls"] = True
            body["tool_choice"] = self._translate_tool_choice(tool_choice)

        rf = _response_format_dict(response_format)
        if rf:
            if rf.get("schema"):
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": rf.get("name", "out"),
                        "schema": rf["schema"],
                        "strict": rf.get("strict", True),
                    },
                }
            elif rf.get("type") == "json_object":
                body["response_format"] = {"type": "json_object"}

        reasoning_applied = False
        if reasoning and reasoning != "off" and self._supports_reasoning(m):
            body["reasoning_effort"] = reasoning
            reasoning_applied = True

        headers = {
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
        if r.status_code != 200:
            raise ProviderError(
                f"openai HTTP {r.status_code}: {r.text[:400]}",
                status=r.status_code,
                retryable=(r.status_code not in (400, 401, 403)),
            )

        d = r.json()
        choices = d.get("choices") or []
        if not choices:
            raise ProviderError(f"openai no choices: {json.dumps(d)[:200]}", status=200, retryable=True)
        msg = choices[0].get("message") or {}
        text = self._extract_text(msg.get("content"))
        tool_calls_out = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            tool_calls_out.append({
                "id": tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                "name": fn.get("name", ""),
                "arguments": _json_loads_maybe(fn.get("arguments") or {}),
            })
        finish_reason = choices[0].get("finish_reason") or "stop"
        usage = d.get("usage") or {}
        return {
            "text": text,
            "tool_calls": tool_calls_out,
            "input_tokens": usage.get("prompt_tokens", 0) or 0,
            "output_tokens": usage.get("completion_tokens", 0) or 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "stop_reason": "tool_use" if tool_calls_out else (
                "max_tokens" if finish_reason == "length" else "end_turn"
            ),
            "model": m,
            "tool_call_dialect": "native",
            "reasoning_applied": reasoning_applied,
        }


# ────────────────────────────────────────────────────────────────────────────
# Anthropic
# ────────────────────────────────────────────────────────────────────────────

_ANTHROPIC_THINKING_BUDGETS = {"low": 1024, "medium": 5000, "high": 10000}


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    capabilities = {
        "tools": True, "caching": False, "reasoning": True,
        "structured": True, "parallel_tools": True, "images": True,
    }

    def __init__(self, api_key: str, model: str):
        super().__init__(api_key, model, "https://api.anthropic.com/v1")

    @staticmethod
    def _message_block_text(text: str) -> dict:
        return {"type": "text", "text": text}

    def _append_message(self, out: list[dict], role: str, blocks: list[dict]) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            prev = out[-1]["content"]
            if isinstance(prev, str):
                prev = [self._message_block_text(prev)]
                out[-1]["content"] = prev
            prev.extend(blocks)
            return
        out.append({"role": role, "content": blocks})

    def _translate_messages(self, messages) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "user":
                content = m.get("content")
                if isinstance(content, list):
                    text_parts, image_parts = _split_content_blocks(content)
                    blocks = [self._message_block_text(text) for text in text_parts]
                    blocks.extend({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image["media_type"],
                            "data": image["data"],
                        },
                    } for image in image_parts)
                else:
                    blocks = [self._message_block_text(_message_text(content))]
                self._append_message(out, "user", blocks)
                continue
            if role == "assistant":
                blocks = []
                text = _message_text(m.get("content"))
                if text:
                    blocks.append(self._message_block_text(text))
                for tc in m.get("tool_calls") or []:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc.get("arguments") or {},
                    })
                self._append_message(out, "assistant", blocks)
                continue
            if role == "tool":
                tool_content = m.get("content")
                if not isinstance(tool_content, str):
                    tool_content = json.dumps(tool_content)
                self._append_message(out, "user", [{
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id") or "",
                    "content": [{"type": "text", "text": tool_content}],
                }])
        return out

    def _translate_tools(self, tools) -> list[dict] | None:
        if not tools:
            return None
        out = []
        for t in tools:
            d = t if isinstance(t, dict) else t.model_dump()
            out.append({
                "name": d["name"],
                "description": d.get("description", ""),
                "input_schema": d.get("input_schema") or {"type": "object", "properties": {}},
            })
        return out

    def _translate_tool_choice(self, tool_choice: Any) -> Any:
        if tool_choice in (None, "auto"):
            return {"type": "auto"}
        if tool_choice == "none":
            return {"type": "none"}
        if isinstance(tool_choice, dict) and tool_choice.get("name"):
            return {"type": "tool", "name": tool_choice["name"]}
        return tool_choice

    @staticmethod
    def _supports_thinking(model: str) -> bool:
        m = model.lower()
        return (
            "claude-3-7-sonnet" in m
            or "claude-sonnet-4" in m
            or "claude-opus-4" in m
        )

    async def chat(self, messages, *, max_tokens=2048, temperature=0.7, model=None,
                   tools=None, tool_choice=None, reasoning=None, response_format=None,
                   system_blocks=None, cache_system=False):
        del cache_system
        m = model or self.model
        system_text, _, _ = _flatten_system(system_blocks)
        body: dict[str, Any] = {
            "model": m,
            "messages": self._translate_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_text:
            body["system"] = system_text

        translated_tools = self._translate_tools(tools)
        if translated_tools and tool_choice != "none":
            body["tools"] = translated_tools
            body["tool_choice"] = self._translate_tool_choice(tool_choice)

        rf = _response_format_dict(response_format)
        if rf:
            schema = rf.get("schema")
            if schema:
                # Anthropic's native structured-output API constrains the
                # assistant's text directly. Keep the gateway-level
                # jsonschema validation in main.py as defense in depth.
                body["output_config"] = {
                    "format": {
                        "type": "json_schema",
                        "schema": _anthropic_clean_schema(schema),
                    }
                }
            else:
                raise ProviderError(
                    "anthropic structured output requires a JSON schema",
                    status=400,
                    retryable=False,
                )

        reasoning_applied = False
        if reasoning and reasoning != "off" and self._supports_thinking(m):
            body["thinking"] = {
                "type": "enabled",
                "budget_tokens": _ANTHROPIC_THINKING_BUDGETS[reasoning],
            }
            reasoning_applied = True

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(f"{self.base_url}/messages", headers=headers, json=body)
            if r.status_code == 400 and reasoning_applied:
                body.pop("thinking", None)
                reasoning_applied = False
                r = await c.post(f"{self.base_url}/messages", headers=headers, json=body)
        if r.status_code != 200:
            raise ProviderError(
                f"anthropic HTTP {r.status_code}: {r.text[:400]}",
                status=r.status_code,
                retryable=(r.status_code not in (400, 401, 403)),
            )

        d = r.json()
        content = d.get("content") or []
        text = "".join(block.get("text", "") for block in content if block.get("type") == "text")
        tool_calls_out = []
        for block in content:
            if block.get("type") == "tool_use":
                tool_calls_out.append({
                    "id": block.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "name": block.get("name", ""),
                    "arguments": block.get("input") or {},
                })
        usage = d.get("usage") or {}
        stop_reason = d.get("stop_reason") or "end_turn"
        return {
            "text": text,
            "tool_calls": tool_calls_out,
            "input_tokens": usage.get("input_tokens", 0) or 0,
            "output_tokens": usage.get("output_tokens", 0) or 0,
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0) or 0,
            "stop_reason": "tool_use" if tool_calls_out else (
                "max_tokens" if stop_reason == "max_tokens" else "end_turn"
            ),
            "model": m,
            "tool_call_dialect": "native",
            "reasoning_applied": reasoning_applied,
        }


# ────────────────────────────────────────────────────────────────────────────
# Gemini
# ────────────────────────────────────────────────────────────────────────────

class GeminiProvider(BaseProvider):
    name = "gemini"
    capabilities = {
        "tools": True, "caching": True, "reasoning": True,
        "structured": True, "parallel_tools": True, "images": True,
    }

    def __init__(self, api_key, model, cache_store):
        super().__init__(api_key, model, "https://generativelanguage.googleapis.com/v1beta")
        self.cache_store = cache_store  # cache.GeminiCache

    def _translate_tools(self, tools):
        if not tools:
            return None
        decls = []
        for t in tools:
            d = t if isinstance(t, dict) else t.model_dump()
            decls.append({
                "name": d["name"],
                "description": d.get("description", ""),
                "parameters": d.get("input_schema") or {"type": "object", "properties": {}},
            })
        return [{"function_declarations": decls}]

    def _translate_messages(self, messages):
        contents = []
        for m in messages:
            r = m.get("role")
            if r == "system":
                continue
            if r == "tool":
                contents.append({
                    "role": "user",
                    "parts": [{
                        "function_response": {
                            "name": m.get("tool_name") or m.get("name") or "tool",
                            "response": _coerce_obj(m.get("content")),
                        }
                    }],
                })
                continue
            if r == "assistant":
                parts = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                for tc in (m.get("tool_calls") or []):
                    part = {
                        "functionCall": {
                            "name": tc["name"],
                            "args": tc.get("arguments") or {},
                        }
                    }
                    meta = tc.get("provider_meta") or {}
                    if meta.get("thoughtSignature"):
                        part["thoughtSignature"] = meta["thoughtSignature"]
                    parts.append(part)
                if not parts:
                    parts = [{"text": ""}]
                contents.append({"role": "model", "parts": parts})
                continue
            content = m.get("content", "")
            if isinstance(content, list):
                text_parts, image_parts = _split_content_blocks(content)
                parts = [{"text": text} for text in text_parts]
                parts.extend({
                    "inline_data": {
                        "mime_type": image["media_type"],
                        "data": image["data"],
                    }
                } for image in image_parts)
            else:
                parts = [{"text": _message_text(content)}]
            contents.append({"role": "user", "parts": parts})
        return contents

    async def chat(self, messages, *, max_tokens=2048, temperature=0.7, model=None,
                   tools=None, tool_choice=None, reasoning=None, response_format=None,
                   system_blocks=None, cache_system=False):
        m = model or self.model
        system_text, blocks, has_cache_marker = _flatten_system(system_blocks)
        cacheable_text = None
        if cache_system or has_cache_marker:
            if has_cache_marker:
                cacheable_text = "\n".join(b["text"] for b in blocks if b["cache"])
            else:
                cacheable_text = system_text
        cache_name = None
        cache_create_tokens = 0
        cache_read_tokens = 0
        if cacheable_text and len(cacheable_text) > 1000:
            cache_name, cache_create_tokens = await self.cache_store.get_or_create(
                self.api_key, m, cacheable_text, self.base_url
            )
            if cache_name and cache_create_tokens == 0:
                cache_read_tokens = len(cacheable_text) // 4

        body: dict[str, Any] = {
            "contents": self._translate_messages(messages),
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        if cache_name:
            body["cachedContent"] = cache_name
            remaining_sys = "\n".join(b["text"] for b in blocks if not b["cache"]) if has_cache_marker else ""
            if remaining_sys:
                body["systemInstruction"] = {"parts": [{"text": remaining_sys}]}
        elif system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}

        if tools:
            body["tools"] = self._translate_tools(tools)
            mode = "AUTO"
            if tool_choice == "none":
                mode = "NONE"
            elif isinstance(tool_choice, dict):
                mode = "ANY"
            body["toolConfig"] = {"function_calling_config": {"mode": mode}}

        if response_format:
            rf = response_format if isinstance(response_format, dict) else response_format.model_dump(by_alias=True)
            if rf.get("schema"):
                body["generationConfig"]["responseMimeType"] = "application/json"
                body["generationConfig"]["responseSchema"] = _gemini_clean_schema(rf["schema"])
            elif rf.get("type") == "json_object":
                body["generationConfig"]["responseMimeType"] = "application/json"

        reasoning_applied = False
        if reasoning and reasoning != "off":
            knob = _gemini_thinking_knob(m)
            if knob == "level":
                body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": reasoning}
                reasoning_applied = True
            elif knob == "budget":
                body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": _GEMINI_BUDGETS[reasoning]}
                reasoning_applied = True

        url = f"{self.base_url}/models/{m}:generateContent?key={self.api_key}"
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(url, json=body)
            if r.status_code != 200:
                if r.status_code == 400:
                    if reasoning_applied:
                        body["generationConfig"].pop("thinkingConfig", None)
                        reasoning_applied = False
                    if "cachedContent" in body and "cache" in r.text.lower():
                        body.pop("cachedContent", None)
                        if system_text:
                            body["systemInstruction"] = {"parts": [{"text": system_text}]}
                        cache_name = None
                        cache_read_tokens = 0
                    r = await c.post(url, json=body)
                if r.status_code != 200:
                    raise ProviderError(
                        f"gemini HTTP {r.status_code}: {r.text[:400]}",
                        status=r.status_code,
                        retryable=(r.status_code not in (400, 401)),
                    )
            d = r.json()
            cands = d.get("candidates") or []
            if not cands:
                raise ProviderError(f"gemini no candidates: {json.dumps(d)[:200]}", status=200, retryable=True)
            parts = cands[0].get("content", {}).get("parts", []) or []
            text = "".join(p.get("text", "") for p in parts if "text" in p)
            tool_calls_out = []
            for p in parts:
                fc = p.get("functionCall") or p.get("function_call")
                if fc:
                    tc = {
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "name": fc.get("name", ""),
                        "arguments": fc.get("args") or fc.get("arguments") or {},
                    }
                    sig = p.get("thoughtSignature") or p.get("thought_signature")
                    if sig:
                        tc["provider_meta"] = {"thoughtSignature": sig}
                    tool_calls_out.append(tc)
            usage = d.get("usageMetadata") or {}
            in_tok = usage.get("promptTokenCount", 0) or 0
            out_tok = usage.get("candidatesTokenCount", 0) or 0
            cached_tok = usage.get("cachedContentTokenCount", 0) or 0
            if cached_tok and not cache_read_tokens:
                cache_read_tokens = cached_tok
            stop = (cands[0].get("finishReason") or "STOP").upper()
            stop_norm = "tool_use" if tool_calls_out else (
                "max_tokens" if stop == "MAX_TOKENS" else "end_turn"
            )
            return {
                "text": text,
                "tool_calls": tool_calls_out,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cache_creation_input_tokens": cache_create_tokens,
                "cache_read_input_tokens": cache_read_tokens,
                "stop_reason": stop_norm,
                "model": m,
                "tool_call_dialect": "native",
                "reasoning_applied": reasoning_applied,
            }


def _gemini_supports_thinking(model: str) -> bool:
    return _gemini_thinking_knob(model) is not None


def _gemini_thinking_knob(model: str) -> Optional[str]:
    """Returns 'level' for thinkingLevel-capable models, 'budget' for thinkingBudget-only, None otherwise."""
    m = (model or "").lower()
    if "gemini" not in m:
        return None
    if "flash-lite" in m:
        return None
    if "2.5-pro" in m or "3-pro" in m or "3.1-pro" in m:
        return "level"
    if "3-flash" in m or "3.1-flash" in m:
        return "level"
    if "2.5-flash" in m:
        return "budget"
    return None


_GEMINI_BUDGETS = {"low": 2048, "medium": 8192, "high": 24576}


def _gemini_inline_refs(schema: dict) -> dict:
    """Resolve `$ref` references to `$defs` / `definitions` inline.

    Pydantic emits refs for nested models. Gemini's responseSchema endpoint
    rejects `$ref`, so we inline before cleaning.
    """
    if not isinstance(schema, dict):
        return schema
    defs = dict(schema.get("$defs") or schema.get("definitions") or {})

    def walk(node, seen: frozenset[str] = frozenset()) -> dict | list:
        if isinstance(node, dict):
            if "$ref" in node:
                target = node["$ref"]
                name = None
                if target.startswith("#/$defs/"):
                    name = target.removeprefix("#/$defs/")
                elif target.startswith("#/definitions/"):
                    name = target.removeprefix("#/definitions/")
                if name and name in defs and name not in seen:
                    resolved = walk(defs[name], seen | {name})
                    extras = {k: walk(v, seen) for k, v in node.items() if k != "$ref"}
                    if isinstance(resolved, dict):
                        return {**resolved, **extras}
                    return resolved
                return {k: walk(v, seen) for k, v in node.items() if k != "$ref"}
            return {k: walk(v, seen) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(x, seen) for x in node]
        return node

    return walk(schema)  # type: ignore[return-value]


def _gemini_clean_schema(schema: dict) -> dict:
    """Strip JSON-Schema keys Gemini rejects, after inlining `$ref` / `$defs`."""
    schema = _gemini_inline_refs(schema)
    if not isinstance(schema, dict):
        return schema
    drop = {"additionalProperties", "$schema", "title", "definitions", "$defs", "examples", "default"}

    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k not in drop}
        if isinstance(node, list):
            return [strip(x) for x in node]
        return node

    return strip(schema)


def _coerce_obj(v):
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return {"text": v}
    return {"value": v}


# ────────────────────────────────────────────────────────────────────────────
# Ollama
# ────────────────────────────────────────────────────────────────────────────

OLLAMA_TOOL_MODELS = ("llama3.1", "llama3.2", "llama3.3", "qwen2.5", "qwen3",
                     "mistral-nemo", "mistral-small", "command-r", "firefunction")
OLLAMA_IMAGE_MODELS = ("gemma4", "moondream", "llava", "qwen2-vl", "qwen2.5-vl",
                       "qwen2.5vl", "minicpm-v", "llama3.2-vision")


def _ollama_native_tools(model: str) -> bool:
    m = (model or "").lower()
    return any(h in m for h in OLLAMA_TOOL_MODELS)


def _ollama_supports_images(model: str) -> bool:
    m = (model or "").lower()
    return any(h in m for h in OLLAMA_IMAGE_MODELS)


class OllamaProvider(BaseProvider):
    name = "ollama"
    capabilities = {
        "tools": True, "caching": False, "reasoning": False,
        "structured": True, "parallel_tools": False, "images": False,
    }

    def __init__(self, model, base_url="http://localhost:11434"):
        super().__init__("", model, base_url)
        self.capabilities = dict(self.capabilities)
        self.capabilities["images"] = _ollama_supports_images(model)

    def _translate_messages(self, messages, system_text, prompted_fallback=False):
        out = []
        if system_text:
            out.append({"role": "system", "content": system_text})
        for m in messages:
            r = m.get("role")
            if r == "system":
                if not system_text:
                    out.append({"role": "system", "content": m.get("content", "")})
                continue
            if r == "tool":
                if prompted_fallback:
                    out.append({
                        "role": "user",
                        "content": "tool_result " + json.dumps({
                            "id": m.get("tool_call_id", ""),
                            "output": m.get("content", ""),
                        }),
                    })
                else:
                    out.append({"role": "tool", "content": m.get("content", "") if isinstance(m.get("content"), str) else json.dumps(m.get("content"))})
                continue
            if r == "assistant" and m.get("tool_calls"):
                tcs = []
                for tc in m["tool_calls"]:
                    tcs.append({"function": {"name": tc["name"], "arguments": tc.get("arguments") or {}}})
                out.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": tcs})
                continue
            content = m.get("content", "")
            if isinstance(content, list):
                text_parts, image_parts = _split_content_blocks(content)
                translated = {"role": r, "content": "\n".join(text_parts)}
                if image_parts:
                    translated["images"] = [image["data"] for image in image_parts]
                out.append(translated)
            else:
                out.append({"role": r, "content": content})
        return out

    async def chat(self, messages, *, max_tokens=2048, temperature=0.7, model=None,
                   tools=None, tool_choice=None, reasoning=None, response_format=None,
                   system_blocks=None, cache_system=False):
        m = model or self.model
        system_text, _, _ = _flatten_system(system_blocks)
        native = _ollama_native_tools(m) and tools
        prompted_fallback = bool(tools) and not native

        if prompted_fallback:
            system_text = (system_text + "\n\n" if system_text else "") + _prompted_tool_system(tools)

        body = {
            "model": m,
            "messages": self._translate_messages(messages, system_text, prompted_fallback=prompted_fallback),
            "options": {"temperature": temperature, "num_predict": max_tokens},
            # This adapter advertises reasoning=False.  Make that contract
            # real for thinking-capable Ollama models instead of allowing
            # hidden reasoning to consume the entire visible-output budget.
            "think": False,
            "stream": False,
        }
        if native:
            body["tools"] = [{
                "type": "function",
                "function": {
                    "name": (t if isinstance(t, dict) else t.model_dump())["name"],
                    "description": (t if isinstance(t, dict) else t.model_dump()).get("description", ""),
                    "parameters": (t if isinstance(t, dict) else t.model_dump()).get("input_schema") or {"type": "object", "properties": {}},
                },
            } for t in tools]

        if response_format:
            rf = response_format if isinstance(response_format, dict) else response_format.model_dump(by_alias=True)
            if rf.get("schema"):
                body["format"] = rf["schema"]
            elif rf.get("type") == "json_object":
                body["format"] = "json"

        async with httpx.AsyncClient(timeout=600) as c:
            r = await c.post(f"{self.base_url}/api/chat", json=body)
            if r.status_code != 200:
                raise ProviderError(f"ollama HTTP {r.status_code}: {r.text[:300]}", status=r.status_code)
            d = r.json()
            msg = d.get("message", {}) or {}
            text = msg.get("content", "") or ""
            tool_calls_out = []
            for tc in (msg.get("tool_calls") or []):
                fn = tc.get("function") or {}
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try: args = json.loads(args)
                    except Exception: args = {"_raw": args}
                tool_calls_out.append({
                    "id": tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "name": fn.get("name", ""),
                    "arguments": args,
                })

            dialect = "native" if native else ("prompted_fallback" if prompted_fallback else "none")
            if prompted_fallback and not tool_calls_out:
                parsed = _parse_prompted_tool_call(text)
                if parsed:
                    tool_calls_out = [parsed]
                    text = ""

            return {
                "text": text,
                "tool_calls": tool_calls_out,
                "input_tokens": d.get("prompt_eval_count", 0) or 0,
                "output_tokens": d.get("eval_count", 0) or 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "stop_reason": (
                    "tool_use"
                    if tool_calls_out
                    else (
                        "max_tokens"
                        if d.get("done_reason") in {"length", "max_tokens"}
                        else "end_turn"
                    )
                ),
                "model": m,
                "tool_call_dialect": dialect,
                "reasoning_applied": False,
            }


def _prompted_tool_system(tools):
    descs = []
    for t in tools:
        d = t if isinstance(t, dict) else t.model_dump()
        descs.append(f"- {d['name']}: {d.get('description','')} schema={json.dumps(d.get('input_schema') or {})}")
    return (
        "When you need to call a tool, respond with ONLY a JSON line of the form "
        '{"tool_call":{"name":"<tool>","arguments":{...}}}. '
        "Do not add prose. Tools available:\n" + "\n".join(descs)
    )


def _parse_prompted_tool_call(text: str):
    if not text:
        return None
    m = re.search(r'\{[\s\S]*"tool_call"[\s\S]*\}', text)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        tc = d.get("tool_call") or {}
        return {
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "name": tc.get("name", ""),
            "arguments": tc.get("arguments") or {},
        }
    except Exception:
        return None


# ────────────────────────────────────────────────────────────────────────────
# Per-model capability resolution
# ────────────────────────────────────────────────────────────────────────────

def model_capabilities(provider_name: str, model: str, default_caps: dict) -> dict:
    caps = dict(default_caps)
    if provider_name in ("gemma", "ollama"):
        images = _ollama_supports_images(model)
        caps.update({
            "tools": True, "reasoning": False, "structured": False,
            "vision": images, "images": images,
        })
    elif provider_name.startswith("gemini"):
        caps.update({
            "reasoning": _gemini_supports_thinking(model),
            "structured": True, "tools": True, "vision": True, "images": True,
        })
    elif provider_name.startswith("openai"):
        caps.update({
            "tools": True, "structured": True,
            "reasoning": OpenAIProvider._supports_reasoning(model),
            "vision": True, "images": True,
        })
    elif provider_name.startswith("anthropic"):
        caps.update({
            "tools": True, "structured": True,
            "reasoning": True, "vision": True, "images": True,
        })
    return caps


def build_providers(cache_store):
    out = {}
    # Local Gemma chat is deliberately opt-in because loading it consumes
    # substantial RAM and can force a laptop into swap. This toggle does not
    # affect Ollama-backed embeddings (`nomic-embed-text`), which are built by
    # `embedders.py` through a separate path.
    if os.getenv("ENABLE_OLLAMA_CHAT", "0") == "1":
        url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        p = OllamaProvider(os.getenv("OLLAMA_MODEL", "gemma4:12b"), url)
        p.name = "gemma"
        out["gemma"] = p
    if os.getenv("ENABLE_PHI4_CHAT", "0") == "1":
        # Deliberately not configurable through OLLAMA_MODEL: this provider's
        # name and the document-segmentation profile are an exact model pin.
        url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        p = OllamaProvider("phi4:14b-q4_K_M", url)
        p.name = "phi4-local"
        out["phi4-local"] = p
    # Exact local image-model pin. It is intentionally outside LLM_ORDER and
    # cannot fall through to a cloud provider when selected by its profile.
    url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    p = OllamaProvider("gemma4:12b", url)
    p.name = "cover-vision-local"
    out["cover-vision-local"] = p

    # ── GEMINI BLOCK ──────────────────────────────────────────
    if os.getenv("ENABLE_GEMINI", "1") != "0":
        if k := os.getenv("GEMINI_API_KEY"):
            def _gemini(key, env, default):
                provider = GeminiProvider(k, os.getenv(env, default), cache_store)
                provider.name = key
                return provider
            out["gemini-cheap"] = _gemini("gemini-cheap", "GEMINI_CHEAP_MODEL", "gemini-2.0-flash-lite")
            out["gemini-flash"] = _gemini("gemini-flash", "GEMINI_FLASH_MODEL", "gemini-2.5-flash")
            out["gemini-pro"] = _gemini("gemini-pro", "GEMINI_PRO_MODEL", "gemini-2.5-pro")

    # ── OPENAI BLOCK ──────────────────────────────────────────
    if os.getenv("ENABLE_OPENAI", "1") != "0":
        if k := os.getenv("OPENAI_API_KEY"):
            def _openai(name, env, default):
                provider = OpenAIProvider(k, os.getenv(env, default))
                provider.name = name
                return provider
            out["openai-cheap"] = _openai("openai-cheap", "OPENAI_CHEAP_MODEL", "gpt-5.4-nano")
            out["openai-mini"] = _openai("openai-mini", "OPENAI_MINI_MODEL", "gpt-5.4-mini")
            out["openai-pro"] = _openai("openai-pro", "OPENAI_PRO_MODEL", "gpt-5.5")

    # ── ANTHROPIC BLOCK ───────────────────────────────────────
    if os.getenv("ENABLE_ANTHROPIC", "1") != "0":
        if k := os.getenv("ANTHROPIC_API_KEY"):
            def _anthropic(name, env, default):
                provider = AnthropicProvider(k, os.getenv(env, default))
                provider.name = name
                return provider
            out["anthropic-haiku"] = _anthropic("anthropic-haiku", "ANTHROPIC_HAIKU_MODEL", "claude-haiku-4-5")
            out["anthropic-sonnet"] = _anthropic("anthropic-sonnet", "ANTHROPIC_SONNET_MODEL", "claude-sonnet-4-6")
            out["anthropic-opus"] = _anthropic("anthropic-opus", "ANTHROPIC_OPUS_MODEL", "claude-opus-4-8")

    return out
