"""Gateway-owned observability reads."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from gateway.app.dependencies import DependencyContainer, get_container
from gateway.app.router_registry import RouterRegistration

router = APIRouter()
Container = Annotated[DependencyContainer, Depends(get_container)]


@router.get("/traces/recent")
def recent_traces(container: Container, limit: int = 25) -> dict[str, Any]:
    return {**container.telemetry.describe(), "traces": container.telemetry.recent.summaries(limit)}


@router.get("/traces/{trace_id}")
def trace_detail(trace_id: str, container: Container) -> dict[str, Any]:
    detail = container.telemetry.recent.detail(trace_id)
    if detail is None:
        raise HTTPException(404, "trace not in this process's ring (it may still be in the trace backend)")
    return detail


@router.get("/refusals")
def refusals(container: Container, limit: int = 25) -> dict[str, Any]:
    return container.telemetry.refusals.describe(limit)


def registrations() -> tuple[RouterRegistration, ...]:
    return (RouterRegistration(router, "/api/observability", ("observability",)),)
