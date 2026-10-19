"""Lifespan-owned facade used only by Gateway's LLM HTTP routes."""

from __future__ import annotations

import asyncio
from pathlib import Path
import time
from typing import Any

from fastapi import HTTPException
from gateway.config import load_mapping
from gateway.ledger import CallLedger
from gateway.llm.economics import BudgetController, PricingTable
from gateway.llm.economics.budget import _period_start
from gateway.llm.models import ChatRequest, EmbedRequest
from gateway.llm.orchestration.budget import BudgetReservationStage
from gateway.llm.orchestration.finalization import FinalizationStage
from gateway.llm.orchestration.normalization import NormalizationStage
from gateway.llm.orchestration.pipeline import LLMPipeline
from gateway.llm.orchestration.profile_resolution import ProfileResolutionStage
from gateway.llm.orchestration.provider_call import ProviderCallStage
from gateway.llm.orchestration.routing import RoutingStage
from gateway.llm.orchestration.structured_output import StructuredOutputStage
from gateway.llm.orchestration.validation import RequestValidationStage
from gateway.llm.profiles import ProfileError, ProfileRegistry
from gateway.llm.providers.base import ProviderError
from gateway.llm.providers.registry import ProviderRegistry, build_provider_registry


class LLMService:
    def __init__(self, *, registry: ProviderRegistry, profiles: ProfileRegistry,
                 pricing: PricingTable, budget: BudgetController, ledger: CallLedger,
                 max_retries: int = 1, max_concurrency: int = 32) -> None:
        self.registry, self.profiles, self.pricing = registry, profiles, pricing
        self.budget, self.ledger = budget, ledger
        self.pipeline = LLMPipeline(validation=RequestValidationStage(), profiles=ProfileResolutionStage(profiles),
            normalization=NormalizationStage(), routing=RoutingStage(registry),
            budget=BudgetReservationStage(budget, pricing), provider_call=ProviderCallStage(max_retries=max_retries, max_concurrency=max_concurrency),
            structured=StructuredOutputStage(), finalization=FinalizationStage(ledger, budget, pricing))

    @classmethod
    def build(cls, *, config_dir: Path, ledger: CallLedger) -> "LLMService":
        registry = build_provider_registry(config_dir=config_dir)
        calls = load_mapping(config_dir / "providers.yaml")
        profiles = ProfileRegistry.from_yaml(config_dir / "profiles.yaml")
        pricing = PricingTable.from_yaml(config_dir / "pricing.yaml")
        budget = BudgetController(config_dir / "budgets.yaml", ledger.database.path)
        return cls(registry=registry, profiles=profiles, pricing=pricing, budget=budget, ledger=ledger,
                   max_retries=int(calls["max_retries"]), max_concurrency=int(calls["max_concurrency"]))

    def attach_tracer(self, tracer: Any) -> None:
        self.pipeline.tracer = tracer

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        return await self.pipeline.run(request)

    async def embed(self, request: EmbedRequest) -> dict[str, Any]:
        started = time.monotonic(); attempts: list[dict[str, Any]] = []; error: BaseException | None = None; selected = request.provider; model = request.model; expected_dim = None
        if request.profile:
            if request.provider or request.model: raise HTTPException(400, "embedding profile is mutually exclusive with provider/model")
            try: spec = self.profiles.resolve("embedding", request.profile)
            except ProfileError as exc: raise HTTPException(400, str(exc)) from exc
            selected, model, expected_dim = spec["provider"], spec["model"], spec["dim"]
        candidates = self.registry.candidates(selected)
        if not candidates: raise HTTPException(503, f"no embedding provider configured for '{selected or 'any'}'")
        result: dict[str, Any] | None = None
        try:
            for provider in candidates:
                if not provider.capabilities.embeddings: continue
                try:
                    vector = await provider.embed(request.text, model=model, task_type=request.task_type)
                    if expected_dim is not None and len(vector) != expected_dim: raise ProviderError(f"embedding profile '{request.profile}' expected dimension {expected_dim} but provider '{provider.name}' returned {len(vector)}")
                    result = {"provider": provider.name, "model": model or provider.model, "embedding": vector, "dim": len(vector), "latency_ms": int((time.monotonic() - started) * 1000), "attempted": attempts, "profile": request.profile}; return result
                except BaseException as exc:
                    error = exc; attempts.append({"provider": provider.name, "reason": str(exc)[:120]})
                    if selected: break
            raise HTTPException(502 if selected else 503, f"embedding providers unavailable. attempts: {attempts}")
        finally:
            await asyncio.to_thread(self.ledger.append, kind="embed", provider=result["provider"] if result else selected or "(any)", model=result["model"] if result else model or "(none)", input_tokens=max(1, len(request.text) // 4), latency_ms=int((time.monotonic() - started) * 1000), status="error" if error else "ok", error=str(error)[:500] if error else None, attempted=attempts, profile=request.profile)


    def providers(self) -> dict[str, Any]:
        return {"order": self.registry.order, "providers": list(self.registry.providers), "models": {name: p.model for name, p in self.registry.providers.items()}, "chat_profiles": {name: {**spec, "available": spec["provider"] in self.registry.providers} for name, spec in self.profiles.all("chat").items()}}

    def capabilities(self) -> dict[str, Any]: return self.registry.diagnostics()
    def today(self) -> dict[str, Any]: return self.ledger.by_provider(since=_period_start("day"))
    def status(self) -> dict[str, Any]: return {"order": self.registry.order, "today": self.today()}
