from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable, Literal, Mapping, Protocol

JsonObject = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __post_init__(self) -> None:
        values = (
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
            self.cache_write_tokens,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
            raise ValueError("token usage values must be non-negative integers")


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    model: str
    messages: tuple[JsonObject, ...]
    system: str | None = None
    tools: tuple[JsonObject, ...] = ()
    max_tokens: int | None = None
    cache: bool = False
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must be a non-empty string")
        if self.max_tokens is not None and (
            not isinstance(self.max_tokens, int)
            or isinstance(self.max_tokens, bool)
            or self.max_tokens <= 0
        ):
            raise ValueError("max_tokens must be a positive integer")

    def with_changes(self, **changes: Any) -> CompletionRequest:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class CompletionResponse:
    content: tuple[JsonObject, ...]
    stop_reason: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    provider_metadata: JsonObject = field(default_factory=dict)


class CompletionProvider(Protocol):
    def __call__(self, request: CompletionRequest) -> Awaitable[CompletionResponse]: ...


IterationRole = Literal["executor", "advisor"]


@dataclass(frozen=True, slots=True)
class IterationUsage:
    ordinal: int
    role: IterationRole
    model: str
    usage: TokenUsage


@dataclass(frozen=True, slots=True)
class GatewayUsage:
    iterations: tuple[IterationUsage, ...]

    @property
    def total(self) -> TokenUsage:
        return TokenUsage(
            input_tokens=sum(item.usage.input_tokens for item in self.iterations),
            output_tokens=sum(item.usage.output_tokens for item in self.iterations),
            cache_read_tokens=sum(item.usage.cache_read_tokens for item in self.iterations),
            cache_write_tokens=sum(item.usage.cache_write_tokens for item in self.iterations),
        )


@dataclass(frozen=True, slots=True)
class GatewayResult:
    response: CompletionResponse
    usage: GatewayUsage
    request_id: str


@dataclass(frozen=True, slots=True)
class AdvisorConfig:
    advisor_model: str
    max_uses: int = 2
    max_tokens: int = 2048
    caching: bool = False
    dummy_input_field: str | None = None
    inject_executor_prompt: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.advisor_model, str) or not self.advisor_model.strip():
            raise ValueError("advisor_model must be a non-empty string")
        if not isinstance(self.max_uses, int) or isinstance(self.max_uses, bool) or self.max_uses < 0:
            raise ValueError("max_uses must be a non-negative integer")
        if (
            not isinstance(self.max_tokens, int)
            or isinstance(self.max_tokens, bool)
            or self.max_tokens <= 0
        ):
            raise ValueError("max_tokens must be a positive integer")
        if self.dummy_input_field is not None and (
            not isinstance(self.dummy_input_field, str) or not self.dummy_input_field.strip()
        ):
            raise ValueError("dummy_input_field must be a non-empty string")


ScoreFunction = Callable[[CompletionResponse], float]
