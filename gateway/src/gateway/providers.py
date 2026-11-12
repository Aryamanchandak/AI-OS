"""Providers: the one place that talks to model vendors, through any-llm.

Contents, in order: the neutral result types, the prompted tool-calling
fallback for local models, the any-llm adapter (`LLMProvider`) and the
registry that builds providers from the environment and `config/`.
This is the only file that imports any-llm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from typing import Any, Protocol, runtime_checkable
import uuid

from any_llm import AnyLLM
from any_llm.exceptions import AnyLLMError, GatewayTimeoutError, UnsupportedParameterError

from gateway.config import load_mapping
from gateway.content import (
    arguments, as_dict, extract_text_blocks, flatten_system, iter_image_blocks, text_of, tool_specs,
)


# --- Result types ----------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    tools: bool = True
    vision: bool = False
    structured_output: bool = True
    reasoning: bool = False
    embeddings: bool = False
    max_context_tokens: int = 128_000

    def as_dict(self) -> dict[str, Any]:
        return {
            "tools": self.tools, "vision": self.vision,
            "structured_output": self.structured_output, "reasoning": self.reasoning,
            "embeddings": self.embeddings, "max_ctx": self.max_context_tokens,
        }


@dataclass(slots=True)
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass(slots=True)
class ProviderResult:
    provider: str
    model: str
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    raw: dict[str, Any] = field(default_factory=dict)
    tool_call_dialect: str = "none"
    reasoning_applied: bool = False


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, status: int = 502, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


@runtime_checkable
class Provider(Protocol):
    name: str
    model: str
    capabilities: ProviderCapabilities

    async def chat(self, *, messages: list[dict[str, Any]], system: Any = None,
                   model: str | None = None, max_tokens: int = 2048,
                   temperature: float = 0.7, tools: list[Any] | None = None,
                   tool_choice: Any = None, response_format: Any = None,
                   reasoning: str | None = None,
                   cache_system: bool = False) -> ProviderResult: ...


    async def embed(self, text: str, *, model: str | None = None,
                    task_type: str = "retrieval_document") -> list[float]: ...

# --- Prompted tool calling for local models without a native tool API ------

#: Model families whose Ollama builds accept a native `tools` array.
NATIVE_TOOL_MODELS = (
    "llama3.1", "llama3.2", "llama3.3", "qwen2.5", "qwen3",
    "mistral-nemo", "mistral-small", "command-r", "firefunction",
)

_CALL_PATTERN = re.compile(r'\{[\s\S]*"tool_call"[\s\S]*\}')


def supports_native_tools(model: str) -> bool:
    return any(hint in (model or "").lower() for hint in NATIVE_TOOL_MODELS)


def prompted_system(tools: list[Any]) -> str:
    """Describe the tool catalogue as a system-prompt instruction."""
    descriptions = [
        f"- {spec['name']}: {spec.get('description', '')} schema={json.dumps(spec.get('input_schema') or {})}"
        for spec in tool_specs(tools)
    ]
    return (
        "When you need to call a tool, respond with ONLY a JSON line of the form "
        '{"tool_call":{"name":"<tool>","arguments":{...}}}. '
        "Do not add prose. Tools available:\n" + "\n".join(descriptions)
    )


def parse_prompted_call(text: str) -> dict[str, Any] | None:
    """Recover a tool call from prose, or None when the reply carries none."""
    if not text:
        return None
    match = _CALL_PATTERN.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    call = payload.get("tool_call") or {}
    return {"id": f"call_{uuid.uuid4().hex[:8]}", "name": call.get("name", ""),
            "arguments": call.get("arguments") or {}}

# --- any-llm adapter -------------------------------------------------------

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

# --- Registry --------------------------------------------------------------

#: Claude and GPT take tools, images, structured output and a reasoning dial.
HOSTED = ProviderCapabilities(tools=True, vision=True, structured_output=True, reasoning=True)


class ProviderRegistry:
    def __init__(self, providers: dict[str, Provider], order: list[str] | None = None) -> None:
        self.providers = providers
        self.order = [x for x in (order or list(providers)) if x in providers]

    def candidates(self, explicit: str | None = None) -> list[Provider]:
        if explicit:
            return [self.providers[explicit]] if explicit in self.providers else []
        return [self.providers[name] for name in self.order]

    def get(self, name: str) -> Provider | None:
        return self.providers.get(name)

    def diagnostics(self) -> dict[str, Any]:
        return {name: {"model": p.model, **p.capabilities.as_dict()} for name, p in self.providers.items()}


def build_provider_registry(*, config_dir: Path) -> ProviderRegistry:
    timeout_s = float(load_mapping(config_dir / "providers.yaml").get("timeout_s", 180))
    providers: dict[str, Provider] = {}
    if key := os.getenv("OPENAI_API_KEY", "").strip():
        providers["openai"] = LLMProvider("openai", "openai", os.getenv("OPENAI_MODEL", "gpt-5.4-nano"), HOSTED,
                                          api_key=key, timeout_s=timeout_s)
    if key := os.getenv("ANTHROPIC_API_KEY", "").strip():
        providers["anthropic"] = LLMProvider("anthropic", "anthropic", os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"), HOSTED,
                                             api_key=key, timeout_s=timeout_s)
    raw = load_mapping(config_dir / "local_models.yaml")
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    for name, spec in (raw.get("models") or {}).items():
        model = os.getenv(spec.get("model_env", ""), spec["model"]) if spec.get("model_env") else spec["model"]
        # A model without a native tool API still gets the prompted fallback, so `tools` is always on.
        capabilities = ProviderCapabilities(tools=True, vision=bool(spec.get("vision")), reasoning=False, embeddings=True,
                                            max_context_tokens=int(spec.get("context_window", 32000)))
        providers[name] = LLMProvider(name, "ollama", model, capabilities, api_base=ollama_url, timeout_s=timeout_s,
                                      needs_think_false=bool(spec.get("needs_think_false")))
    return ProviderRegistry(providers)
