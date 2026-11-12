"""Request and response shapes for the gateway API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolDef(BaseModel):
    """Canonical tool definition. Schema is JSON-Schema (typically from Pydantic)."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    # Optional opaque per-provider metadata
    # that must be echoed back when sending the assistant turn.
    provider_meta: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class CacheableSystemBlock(BaseModel):
    text: str
    cache: bool = False


class ResponseFormat(BaseModel):
    type: Literal["json_schema", "json_object"] = "json_schema"
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    name: str = "out"
    strict: bool = True

    model_config = ConfigDict(populate_by_name=True)


class ChatRequest(BaseModel):
    """Chat input with explicit model/profile selection and agent/session attribution."""

    model_config = ConfigDict(extra="forbid")

    messages: list[dict[str, Any]] | None = None
    prompt: str | None = None
    system: str | list[CacheableSystemBlock] | None = None
    provider: str | None = None
    model: str | None = None
    profile: str | None = None
    max_tokens: int = 2048
    temperature: float = 0.7
    stream: Literal[False] = False

    @field_validator("stream", mode="before")
    @classmethod
    def reject_streaming(cls, value: Any) -> Any:
        if value is True or value == 1 or (isinstance(value, str) and value.lower() in {"true", "1", "yes", "on"}):
            raise ValueError("Streaming is not supported; use stream: false")
        return value

    # New in V2:
    tools: list[ToolDef] | None = None
    tool_choice: str | dict[str, Any] | None = None  # "auto" | "none" | {name}
    cache_system: bool | None = None
    reasoning: Literal["off", "low", "medium", "high"] | None = None
    response_format: ResponseFormat | None = None

    # Free-form attribution tags for spend tracking and budgets.
    agent: str | None = None
    session: str | None = None


class EmbedRequest(BaseModel):
    """Request for POST /api/llm/embed. The model is fixed per deployment (see
    README); only the text, task type, and an optional explicit provider
    are caller-controlled."""

    text: str
    task_type: Literal["retrieval_document", "retrieval_query"] = "retrieval_document"
    provider: str | None = None  # "ollama" | configured fallback name
    model: str | None = None
    profile: str | None = None


class EmbedResponse(BaseModel):
    provider: str
    model: str
    embedding: list[float]
    dim: int
    latency_ms: int = 0
    attempted: list[dict[str, Any]] = Field(default_factory=list)
    profile: str | None = None


class ChatResponse(BaseModel):
    provider: str
    model: str
    profile: str | None = None
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    stop_reason: Literal["tool_use", "end_turn", "max_tokens", "error"] = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    latency_ms: int = 0
    tool_call_dialect: Literal["native", "prompted_fallback", "none"] = "none"
    reasoning_applied: bool = False
    parsed: dict[str, Any] | None = None  # set when response_format used
    attempted: list[dict[str, Any]] = Field(default_factory=list)
    # New in V8: how many automatic retries fired before success (or final fail).
    retries: int = 0

    # ── New in V4. All additive; a V3 client ignores them. ─────────────────
    #: What this call cost, per-model, split by token class.
    cost: dict[str, Any] | None = None
    #: Budget verdict: projected cost, ceilings checked, remaining allowance.
    #: Present whenever a budget policy governed the principal.
    budget: dict[str, Any] | None = None
    #: OTel trace/span ids, so a caller can jump straight to the waterfall.
    trace: dict[str, Any] | None = None


class PreflightRequest(BaseModel):
    chat_profile: str | None = None
    chat_provider: str | None = None
    chat_model: str | None = None
    embedding_profile: str = "chunker-v1"


class PreflightCheck(BaseModel):
    ok: bool
    provider: str | None = None
    model: str | None = None
    latency_ms: int
    profile: str | None = None
    dim: int | None = None
    status_code: int | None = None
    error: str | None = None


class PreflightResponse(BaseModel):
    ok: bool
    chat: PreflightCheck
    embedding: PreflightCheck


class BudgetSetRequest(BaseModel):
    """POST /api/llm/budget — arm or move a ceiling at runtime.

    `principal` is "<dimension>:<value-or-glob>" over the two attribution
    dimensions (agent, session). A runtime entry shadows
    a same-named entry in budgets.yaml, so an operator can clamp a runaway
    session without a deploy, and `limit_usd: 0` refuses everything for that
    principal immediately.
    """

    principal: str = Field(description='e.g. "session:run-42" or "agent:*"')
    limit_usd: float = Field(ge=0)
    period: Literal["minute", "hour", "day", "month", "lifetime"] | None = None
    include_errors: bool | None = None
