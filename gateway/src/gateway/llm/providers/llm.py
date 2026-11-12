"""The only file that imports any-llm: neutral chat/embed requests in, `ProviderResult` out."""

from __future__ import annotations

import json
from typing import Any
import uuid

from any_llm import AnyLLM
from any_llm.exceptions import AnyLLMError, GatewayTimeoutError, UnsupportedParameterError

from gateway.llm.providers.base import ProviderCapabilities, ProviderError, ProviderResult, ProviderUsage
from gateway.llm.providers.content import (
    arguments, as_dict, extract_text_blocks, flatten_system, iter_image_blocks, text_of, tool_specs,
)
from gateway.llm.providers.prompted_tools import parse_prompted_call, prompted_system, supports_native_tools

#: Anthropic `budget_tokens` per reasoning level.
THINKING_BUDGET = {"low": 1024, "medium": 5000, "high": 10000}
#: OpenAI families that accept `reasoning_effort`; sending it to anything else is a 400.
OPENAI_REASONING_FAMILIES = ("o1", "o3", "o4", "gpt-5")


def _error(exc: AnyLLMError) -> ProviderError:
    if isinstance(exc, UnsupportedParameterError):
        return ProviderError(str(exc), status=400)
    if exc.status_code is None:  # timeout or connection failure
        return ProviderError(str(exc), status=504 if isinstance(exc, GatewayTimeoutError) else 502, retryable=True)
    status = exc.status_code
    return ProviderError(str(exc), status=status, retryable=status in {408, 409, 429} or status >= 500)


class LLMProvider:
    """One configured provider instance (`kind` is the any-llm provider: anthropic, openai or ollama)."""

    def __init__(self, name: str, kind: str, model: str, capabilities: ProviderCapabilities, *,
                 api_key: str | None = None, api_base: str | None = None, timeout_s: float = 180.0,
                 needs_think_false: bool = False, client_args: dict[str, Any] | None = None) -> None:
        self.name, self.kind, self.model, self.capabilities = name, kind, model, capabilities
        self.needs_think_false = needs_think_false
        args: dict[str, Any] = {"timeout": timeout_s, **(client_args or {})}
        if kind != "ollama":
            args.setdefault("max_retries", 0)  # retries belong to the provider-call stage
        self.client = AnyLLM.create(kind, api_key=api_key, api_base=api_base, unified_exceptions=True, **args)

    def _messages(self, messages: list[dict[str, Any]], system: Any, *, cache: bool,
                  prompted_tools: str = "") -> list[dict[str, Any]]:
        """Neutral request shape -> OpenAI chat format, which any-llm translates per vendor."""
        text, blocks, has_cache = flatten_system(system)
        out: list[dict[str, Any]] = []
        if self.kind == "anthropic" and blocks and (cache or has_cache) and not prompted_tools:
            # One system message of blocks: any-llm passes it to Anthropic as-is, `cache_control` included.
            out.append({"role": "system", "content": [
                {"type": "text", "text": block["text"], **({"cache_control": {"type": "ephemeral"}} if block["cache"] else {})}
                for block in blocks]})
        elif text := "\n\n".join(part for part in (text, prompted_tools) if part):
            out.append({"role": "system", "content": text})
        for message in messages:
            role, content = message.get("role"), message.get("content")
            if role == "system":
                if not text:
                    out.append({"role": "system", "content": text_of(content)})
            elif role == "tool" and prompted_tools:
                # The prompted dialect has no tool role: show the result as a user turn.
                output = json.dumps(content if isinstance(content, str) else json.dumps(content))
                out.append({"role": "user", "content": f'tool_result {{"id":"{message.get("tool_call_id", "")}","output":{output}}}'})
            elif role == "tool":
                out.append({"role": "tool", "tool_call_id": message.get("tool_call_id") or "", "content": text_of(content)})
            elif role == "assistant" and message.get("tool_calls"):
                out.append({"role": "assistant", "content": text_of(content) or None, "tool_calls": [
                    {"id": call["id"], "type": "function",
                     "function": {"name": call["name"], "arguments": json.dumps(call.get("arguments") or {})}}
                    for call in message["tool_calls"]]})
            elif isinstance(content, list):
                parts: list[dict[str, Any]] = [{"type": "text", "text": value}] if (value := extract_text_blocks(content)) else []
                parts += [{"type": "image_url", "image_url": {"url": f"data:{media};base64,{data}"}}
                          for media, data in iter_image_blocks(content)]
                out.append({"role": role, "content": parts})
            else:
                out.append({"role": role, "content": text_of(content)})
        return out

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None, model: str | None = None,
                   max_tokens: int = 2048, temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None, reasoning: str | None = None,
                   cache_system: bool = False) -> ProviderResult:
        selected = model or self.model
        specs = tool_specs(tools) if tool_choice != "none" else []
        prompted = self.kind == "ollama" and bool(specs) and not supports_native_tools(selected)
        call: dict[str, Any] = {"model": selected, "max_tokens": max_tokens, "temperature": temperature,
                                "messages": self._messages(messages, system, cache=cache_system,
                                                           prompted_tools=prompted_system(specs) if prompted else "")}
        if specs and not prompted:
            call["tools"] = [{"type": "function", "function": {
                "name": spec["name"], "description": spec.get("description", ""),
                "parameters": spec.get("input_schema") or {"type": "object", "properties": {}}}} for spec in specs]
            if self.kind != "ollama":
                call["tool_choice"] = ({"type": "function", "function": {"name": tool_choice["name"]}}
                                       if isinstance(tool_choice, dict) and tool_choice.get("name") else tool_choice or "auto")
            if self.kind == "openai":
                call["parallel_tool_calls"] = True
        if spec := as_dict(response_format):
            if schema := spec.get("schema"):
                call["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": spec.get("name", "out"), "schema": schema, "strict": spec.get("strict", True)}}
            elif spec.get("type") == "json_object":
                call["response_format"] = {"type": "json_object"}
        reasoning_applied = False
        if self.kind == "anthropic" and reasoning in THINKING_BUDGET:
            call["thinking"] = {"type": "enabled", "budget_tokens": THINKING_BUDGET[str(reasoning)]}
            reasoning_applied = True
        elif self.kind == "openai" and reasoning and reasoning != "off" and selected.lower().startswith(OPENAI_REASONING_FAMILIES):
            call["reasoning_effort"] = reasoning
            reasoning_applied = True
        if self.kind == "ollama" and self.needs_think_false:
            call["think"] = False

        try:
            completion = await self.client.acompletion(**call)
        except AnyLLMError as exc:
            raise _error(exc) from exc

        if not completion.choices:
            raise ProviderError(f"{self.name} returned no choices")
        choice = completion.choices[0]
        text = choice.message.content or ""
        calls = [{"id": raw.id or f"call_{uuid.uuid4().hex[:8]}", "name": raw.function.name,
                  "arguments": arguments(raw.function.arguments or {})}
                 for raw in choice.message.tool_calls or [] if hasattr(raw, "function")]
        if prompted and not calls and (parsed := parse_prompted_call(text)):
            calls, text = [parsed], ""
        usage, details = completion.usage, getattr(completion.usage, "prompt_tokens_details", None)
        return ProviderResult(
            # Ollama may report a tag such as `:latest`; the requested name is what profiles pin.
            provider=self.name, model=selected if self.kind == "ollama" else completion.model or selected,
            text=text, tool_calls=calls,
            stop_reason="tool_use" if calls else ("max_tokens" if choice.finish_reason == "length" else "end_turn"),
            usage=ProviderUsage(input_tokens=usage.prompt_tokens if usage else 0,
                                output_tokens=usage.completion_tokens if usage else 0,
                                cache_creation_input_tokens=getattr(details, "cache_write_tokens", 0) or 0,
                                cache_read_input_tokens=getattr(details, "cached_tokens", 0) or 0),
            tool_call_dialect="prompted_fallback" if prompted else ("native" if specs else "none"),
            reasoning_applied=reasoning_applied)

    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]:
        del task_type
        try:
            response = await self.client.aembedding(model or self.model, text)
        except NotImplementedError as exc:
            raise ProviderError(f"{self.kind} does not support embeddings", status=400) from exc
        except AnyLLMError as exc:
            raise _error(exc) from exc
        return list(response.data[0].embedding) if response.data else []
