from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gateway.llm.economics.budget import Admission
from gateway.llm.economics.meter import Principal
from gateway.llm.models import ChatRequest
from gateway.llm.providers.base import Provider, ProviderResult


@dataclass(slots=True)
class PipelineContext:
    request: ChatRequest
    started: float
    principal: Principal
    messages: list[dict[str, Any]] = field(default_factory=list)
    system: Any = None
    prompt_text: str = ""
    estimated_input_tokens: int = 0
    candidates: list[Provider] = field(default_factory=list)
    provider: Provider | None = None
    result: ProviderResult | None = None
    output: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    retries: int = 0
    admission: Admission | None = None
    cache_fields: dict[str, Any] = field(default_factory=dict)
    cache_embedding: list[float] | None = None
    cache_hit: bool = False
    cost: dict[str, Any] | None = None
    error: BaseException | None = None
    finalized: bool = False
