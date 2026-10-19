# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Thin HTTP translation for the LLM domain."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from gateway.app.dependencies import get_llm_service
from gateway.app.router_registry import RouterRegistration
from gateway.llm import LLMService
from gateway.llm.economics.budget import BudgetConfigError, _parse_principal, _period_start
from gateway.llm.economics.meter import DIMENSIONS
from gateway.llm.models import BudgetSetRequest, ChatRequest, EmbedRequest, PreflightRequest, PreflightResponse
from gateway.llm.api.preflight import run_preflight
from gateway.platform.observability.redaction import safe_error

router = APIRouter()


def _chat_trace(result: dict[str, Any]) -> dict[str, Any]:
    from opentelemetry.trace import get_current_span

    span = get_current_span()
    context = span.get_span_context()
    output = dict(result)
    if context.is_valid:
        output["trace"] = {"trace_id": f"{context.trace_id:032x}", "span_id": f"{context.span_id:016x}", "url": None}
        for key, field in (("gen_ai.provider.name", "provider"), ("gen_ai.response.model", "model")):
            if result.get(field) is not None:
                span.set_attribute(key, safe_error(result[field]))
        for key, field in (("gen_ai.usage.input_tokens", "input_tokens"), ("gen_ai.usage.output_tokens", "output_tokens")):
            if isinstance(result.get(field), int):
                span.set_attribute(key, result[field])
        for key, section, field in (("glc.cost.usd", "cost", "total_usd"), ("glc.budget.admitted", "budget", "allowed")):
            value = (result.get(section) or {}).get(field)
            if isinstance(value, (int, float, bool)):
                span.set_attribute(key, value)
    return output


@router.post("/preflight", response_model=PreflightResponse)
async def preflight(request: PreflightRequest, service: Annotated[LLMService, Depends(get_llm_service)]) -> PreflightResponse:
    return await run_preflight(request, service)


@router.post("/chat")
async def chat(request: ChatRequest, service: Annotated[LLMService, Depends(get_llm_service)]):
    return _chat_trace(await service.chat(request))


@router.post("/embed")
async def embed(request: EmbedRequest, service: Annotated[LLMService, Depends(get_llm_service)]): return await service.embed(request)


@router.get("/embedders")
async def embedders(service: Annotated[LLMService, Depends(get_llm_service)]):
    values = {name: provider for name, provider in service.registry.providers.items() if provider.capabilities.embeddings}
    return {"order": list(values), "models": {name: provider.model for name, provider in values.items()}, "today": service.meter.aggregate(), "profiles": service.profiles.all("embedding")}


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
    if status is None: return {"principal": principal, "dimension": dimension, "value": value, "governed": False, "limit_usd": None, "spent_usd": 0.0, "spent_lifetime_usd": 0.0, "message": "No budget policy matches this principal, so it is unlimited. Add one to budgets.yaml or POST /api/llm/budget."}
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


@router.get("/pricing")
async def pricing(service: Annotated[LLMService, Depends(get_llm_service)], provider: str | None = None, model: str | None = None):
    if provider or model:
        value = service.pricing.price_for(provider or "", model); return {"provider": provider, "model": model, "input_usd_per_mtok": value.input_usd_per_mtok, "output_usd_per_mtok": value.output_usd_per_mtok, "cache_read_multiplier": value.cache_read_multiplier, "cache_write_multiplier": value.cache_write_multiplier, "quality": value.quality, "price_source": value.source, "priced": value.priced}
    return service.pricing.describe()


def registration() -> RouterRegistration: return RouterRegistration(router=router, prefix="/api/llm", tags=("llm",))
