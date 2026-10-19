"""Lifespan-owned facade used only by Gateway's LLM HTTP routes."""

from __future__ import annotations

import asyncio
from pathlib import Path
import time
from typing import Any

from fastapi import HTTPException
import httpx

from gateway.audit import AuditStore
from gateway.llm.economics import BudgetController, Meter, PricingTable
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
                 pricing: PricingTable, budget: BudgetController, meter: Meter,
                 audit: AuditStore) -> None:
        self.registry, self.profiles, self.pricing = registry, profiles, pricing
        self.budget, self.meter, self.audit = budget, meter, audit
        self.pipeline = LLMPipeline(validation=RequestValidationStage(), profiles=ProfileResolutionStage(profiles),
            normalization=NormalizationStage(), routing=RoutingStage(registry),
            budget=BudgetReservationStage(budget, pricing), provider_call=ProviderCallStage(),
            structured=StructuredOutputStage(), finalization=FinalizationStage(meter, audit, budget, pricing))

    @classmethod
    def build(cls, *, client: httpx.AsyncClient, config_dir: Path, database_path: Path, audit: AuditStore) -> "LLMService":
        registry = build_provider_registry(client, config_dir=config_dir)
        profiles = ProfileRegistry.from_yaml(config_dir / "profiles.yaml")
        pricing = PricingTable.from_yaml(config_dir / "pricing.yaml")
        budget = BudgetController(config_dir / "budgets.yaml", database_path)
        meter = Meter()
        return cls(registry=registry, profiles=profiles, pricing=pricing, budget=budget, meter=meter, audit=audit)

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
            row: dict[str, Any] = {"provider": result["provider"] if result else selected or "(any)", "model": result["model"] if result else model or "(none)", "principal": {}, "input_tokens": max(1, len(request.text) // 4), "output_tokens": 0, "cost_usd": 0.0, "latency_ms": int((time.monotonic() - started) * 1000), "status": "error" if error else "ok", "error": str(error)[:500] if error else None, "attempted": attempts, "profile": request.profile, "call_role": "embed"}
            self.meter.record(**row)
            await asyncio.to_thread(self.audit.append, channel="llm", channel_user_id="anonymous", trust_level="internal", event_type="llm.embed", params={"profile": request.profile}, result=row)


    def providers(self) -> dict[str, Any]:
        return {"order": self.registry.order, "providers": list(self.registry.providers), "models": {name: p.model for name, p in self.registry.providers.items()}, "chat_profiles": {name: {**spec, "available": spec["provider"] in self.registry.providers} for name, spec in self.profiles.all("chat").items()}}

    def capabilities(self) -> dict[str, Any]: return self.registry.diagnostics()
    def status(self) -> dict[str, Any]: return {"order": self.registry.order, "today": self.meter.aggregate()}
