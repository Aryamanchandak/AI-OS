# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Thin HTTP translation for the LLM domain."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from gateway.app.dependencies import get_llm_service
from gateway.app.router_registry import RouterRegistration
from gateway.llm import LLMService
from gateway.llm.economics.budget import BudgetConfigError, _parse_principal, _period_start
from gateway.llm.economics.meter import DIMENSIONS
from gateway.llm.models import BatchChatRequest, BudgetSetRequest, ChatRequest, EmbedRequest, ResponseFormat, VisionRequest

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest, service: Annotated[LLMService, Depends(get_llm_service)]):
    if request.stream:
        outcome = await service.stream_chat(request)
        # A semantic-cache hit answers with the stored JSON body even on a
        # streaming request, which is what the legacy route does.
        if isinstance(outcome, dict): return outcome
        return StreamingResponse(outcome, media_type="text/event-stream")
    return await service.chat(request)


@router.post("/chat/batch")
async def chat_batch(request: BatchChatRequest, service: Annotated[LLMService, Depends(get_llm_service)]):
    semaphore = asyncio.Semaphore(max(1, request.max_concurrency))
    async def one(call: ChatRequest):
        async with semaphore:
            try: return await service.chat(call)
            except HTTPException as exc: return {"error": str(exc.detail), "status_code": exc.status_code}
            except Exception as exc: return {"error": str(exc)[:400], "status_code": 500}
    return {"results": await asyncio.gather(*(one(call) for call in request.calls))}


@router.post("/vision")
async def vision(request: VisionRequest, service: Annotated[LLMService, Depends(get_llm_service)]):
    inner = ChatRequest(messages=[{"role": "user", "content": [{"type": "text", "text": request.prompt}, {"type": "image_url", "image_url": {"url": request.image}}]}], system=request.system, provider=request.provider, model=request.model, max_tokens=request.max_tokens, temperature=request.temperature, response_format=ResponseFormat(type="json_schema", schema=request.schema_, name=request.schema_name, strict=True) if request.schema_ else None, agent=request.agent, session=request.session, tenant=request.tenant, project=request.project, user=request.user)
    return await service.chat(inner)


@router.post("/embed")
async def embed(request: EmbedRequest, service: Annotated[LLMService, Depends(get_llm_service)]): return await service.embed(request)


@router.get("/embedders")
async def embedders(service: Annotated[LLMService, Depends(get_llm_service)]):
    values = {name: provider for name, provider in service.registry.providers.items() if provider.capabilities.embeddings}
    return {"order": list(values), "models": {name: provider.model for name, provider in values.items()}, "fixed_dim": 768, "max_input_chars": 100000, "backoff_steps_s": [1, 5, 30], "live": {name: {"available": True} for name in values}, "today": service.meter.aggregate(), "profiles": service.profiles.all("embedding")}


@router.get("/providers")
async def providers(service: Annotated[LLMService, Depends(get_llm_service)]): return service.providers()


@router.get("/chat/profiles/{profile}")
async def chat_profile(profile: str, service: Annotated[LLMService, Depends(get_llm_service)]):
    try: return service.profiles.resolve("chat", profile)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc


@router.get("/capabilities")
async def capabilities(service: Annotated[LLMService, Depends(get_llm_service)]): return service.capabilities()


@router.get("/status")
async def status(service: Annotated[LLMService, Depends(get_llm_service)]): return service.status()


@router.get("/routers")
async def routers(service: Annotated[LLMService, Depends(get_llm_service)]): return {"order": [], "providers": [], "models": {}, "live": {}, "today": {}, "limits": {}, "tier_to_order": {}}


@router.get("/calls")
async def calls(service: Annotated[LLMService, Depends(get_llm_service)], limit: int = 100, provider: str | None = None, status: str | None = None): return service.meter.recent(limit, provider, status)


@router.get("/cost/by_agent")
async def cost_by_agent(service: Annotated[LLMService, Depends(get_llm_service)], session: str | None = None, agent: str | None = None):
    rows = service.meter.rollup("agent", value=agent)
    if session: rows = [x for x in rows if x.get("session") == session]
    return rows


@router.get("/budget")
async def list_budgets(service: Annotated[LLMService, Depends(get_llm_service)]): return await asyncio.to_thread(service.budget.describe)


@router.get("/budget/{principal:path}")
async def get_budget(principal: str, service: Annotated[LLMService, Depends(get_llm_service)]):
    try: dimension, value = _parse_principal(principal)
    except BudgetConfigError as exc: raise HTTPException(400, str(exc)) from exc
    status = await asyncio.to_thread(service.budget.status_for, dimension, value)
    if status is None: return {"principal": principal, "dimension": dimension, "value": value, "governed": False, "limit_usd": None, "spent_usd": 0.0, "spent_lifetime_usd": 0.0, "message": "No budget policy matches this principal, so it is unlimited. Add one to budgets.yaml or POST /v1/budget."}
    policy = service.budget.policy_for(dimension, value)
    assert policy is not None
    return {**status.as_dict(), "governed": True, "policy": policy.as_dict()}


@router.post("/budget")
async def set_budget(request: BudgetSetRequest, service: Annotated[LLMService, Depends(get_llm_service)]):
    try: policy = await asyncio.to_thread(service.budget.set_limit, request.principal, request.limit_usd, request.period, request.include_errors)
    except BudgetConfigError as exc: raise HTTPException(400, str(exc)) from exc
    status = await asyncio.to_thread(service.budget.status_for, policy.dimension, policy.pattern)
    return {"ok": True, "policy": policy.as_dict(), "status": status.as_dict() if status else None}


@router.delete("/budget/{principal:path}")
async def delete_budget(principal: str, service: Annotated[LLMService, Depends(get_llm_service)]):
    try: removed = await asyncio.to_thread(service.budget.clear_limit, principal)
    except BudgetConfigError as exc: raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "removed": removed, "principal": principal}


@router.get("/cost/by_principal")
async def cost_by_principal(service: Annotated[LLMService, Depends(get_llm_service)], dimension: str | None = None, value: str | None = None, since: float | None = None, period: str = "day", group_by_provider: bool = True):
    start = since if since is not None else _period_start(period)
    if dimension:
        if dimension not in DIMENSIONS: raise HTTPException(400, f"unknown dimension {dimension!r}; expected one of {list(DIMENSIONS)}")
        rows = service.meter.rollup(dimension, since=start, value=value, group_by_provider=group_by_provider)
        return {"period": period, "since": start, "dimension": dimension, "rows": rows, "total_usd": round(sum(x["dollars"] for x in rows), 8)}
    values = service.meter.rollup_all(since=start)
    return {"period": period, "since": start, "dimensions": list(DIMENSIONS), "by_dimension": values, "totals_usd": {key: round(sum(x["dollars"] for x in rows), 8) for key, rows in values.items()}}


@router.get("/cache/stats")
async def cache_stats(service: Annotated[LLMService, Depends(get_llm_service)]):
    if service.cache is None:
        return {"enabled": False, "message": "semantic cache not initialised"}
    stats = await asyncio.to_thread(service.cache.stats)
    return {**stats, "enabled": service.cache.enabled}


@router.post("/cache/purge")
async def cache_purge(service: Annotated[LLMService, Depends(get_llm_service)], expired_only: bool = True):
    if service.cache is None: raise HTTPException(503, "semantic cache not initialised")
    removed = await asyncio.to_thread(service.cache.purge, expired_only=expired_only)
    return {"ok": True, "removed": removed}


@router.get("/pricing")
async def pricing(service: Annotated[LLMService, Depends(get_llm_service)], provider: str | None = None, model: str | None = None):
    if provider or model:
        value = service.pricing.price_for(provider or "", model); return {"provider": provider, "model": model, "input_usd_per_mtok": value.input_usd_per_mtok, "output_usd_per_mtok": value.output_usd_per_mtok, "cache_read_multiplier": value.cache_read_multiplier, "cache_write_multiplier": value.cache_write_multiplier, "batch_multiplier": value.batch_multiplier, "quality": value.quality, "price_source": value.source, "priced": value.priced}
    return service.pricing.describe()


@router.get("/telemetry")
async def telemetry(): return {"capture_content": False, "enabled": True}


def registration() -> RouterRegistration: return RouterRegistration(router=router, prefix="/api/llm", tags=("llm",))
def alias_registration() -> RouterRegistration: return RouterRegistration(router=router, prefix="/v1", tags=("llm-legacy-deprecated",), deprecated=True)
