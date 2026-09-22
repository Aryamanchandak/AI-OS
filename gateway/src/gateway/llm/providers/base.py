"""Normalized provider protocol and cross-provider value objects."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    streaming: bool = True
    tools: bool = True
    vision: bool = False
    structured_output: bool = True
    reasoning: bool = False
    embeddings: bool = False
    max_context_tokens: int = 128_000

    def as_dict(self) -> dict[str, Any]:
        return {
            "streaming": self.streaming, "tools": self.tools, "vision": self.vision,
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


#: Prefix marking a streamed chunk as a tool-call delta rather than text. The
#: streaming pipeline splits on it to pick the SSE frame key (`tool_call_delta`
#: vs `delta`). Byte-identical to the legacy marker in `glc_v5/glc/providers.py`.
TOOL_CALL_DELTA = "[[TOOL_CALL_DELTA]]"


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

    def stream(self, *, messages: list[dict[str, Any]], system: Any = None,
               model: str | None = None, max_tokens: int = 2048,
               temperature: float = 0.7, tools: list[Any] | None = None,
               tool_choice: Any = None, response_format: Any = None,
               reasoning: str | None = None, cache_system: bool = False,
               result_sink: dict[str, Any] | None = None) -> AsyncIterator[str]: ...

    async def embed(self, text: str, *, model: str | None = None,
                    task_type: str = "retrieval_document") -> list[float]: ...


async def fallback_stream(chat: Any, *, result_sink: dict[str, Any] | None = None,
                          **kwargs: Any) -> AsyncIterator[str]:
    """Buffered stream: call `chat` to completion and yield the text once.

    This is what every provider except the OpenAI-compatible family does in the
    legacy tree (`BaseProvider.stream`), so it is the equivalent behaviour, not a
    stub. Because the whole result is in hand, the model the vendor actually
    resolved to can be published through `result_sink` — which is what lets a
    streamed pinned-profile call be checked against its pin the same way the
    non-streaming path is.
    """
    result: ProviderResult = await chat(**kwargs)
    if result_sink is not None:
        result_sink["model"] = result.model
        result_sink["result"] = result
    if result.text:
        yield result.text


def system_text(system: Any) -> str | None:
    if system is None or isinstance(system, str):
        return system
    return "\n".join(str(getattr(block, "text", block.get("text", "") if isinstance(block, dict) else block)) for block in system)


def openai_messages(messages: list[dict[str, Any]], system: Any) -> list[dict[str, Any]]:
    prefix = system_text(system)
    return ([{"role": "system", "content": prefix}] if prefix else []) + messages


def normalize_stop_reason(value: Any) -> str:
    return {"tool_calls": "tool_use", "tool_use": "tool_use", "length": "max_tokens", "max_tokens": "max_tokens"}.get(str(value), "end_turn")
