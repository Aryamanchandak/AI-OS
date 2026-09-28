"""Gateway-owned observability reads with legacy URL aliases."""
from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
import httpx

from gateway.app.dependencies import DependencyContainer, get_container
from gateway.app.router_registry import RouterRegistration
from gateway.platform.observability.redaction import safe_error

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


@router.get("/agent_trace/{run_id}")
async def agent_trace(
    run_id: str,
    container: Container,
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        target = container.service_registry.url_for("agent_runtime")
    except (KeyError, ValueError):
        raise HTTPException(503, "no agent runtime configured or enabled") from None
    if base_url is not None and base_url.rstrip("/") != target:
        raise HTTPException(400, "base_url must match the configured agent runtime")
    # Encoding the entire identifier prevents path traversal into other agent APIs.
    if not run_id or run_id in {".", ".."}:
        raise HTTPException(422, "invalid run identifier")
    try:
        response = await container.http.client.get(
            f"{target}/v1/agent/runs/{quote(run_id, safe='')}/trace", timeout=10,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "agent runtime is unreachable") from None
    if response.status_code != 200:
        raise HTTPException(response.status_code if 400 <= response.status_code < 600 else 502, "agent runtime could not return this trace")
    try:
        payload = response.json()
    except ValueError:
        raise HTTPException(502, "agent runtime returned invalid trace JSON") from None
    if not isinstance(payload, dict):
        raise HTTPException(502, "agent runtime returned an invalid trace object")

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()
                    if key not in {"prompt", "completion", "gen_ai.input.messages", "gen_ai.output.messages"}}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return safe_error(value) if isinstance(value, str) else value

    return {**clean(payload), "source": target}


def registrations() -> tuple[RouterRegistration, ...]:
    # The old agent URL had an extra /observability component. All aliases
    # reference these functions; there is no second implementation.
    legacy = APIRouter()
    legacy.add_api_route("/traces/recent", recent_traces, methods=["GET"])
    legacy.add_api_route("/traces/{trace_id}", trace_detail, methods=["GET"])
    legacy.add_api_route("/refusals", refusals, methods=["GET"])
    legacy.add_api_route("/observability/agent_trace/{run_id}", agent_trace, methods=["GET"])
    return (
        RouterRegistration(router, "/api/observability", ("observability",)),
        RouterRegistration(legacy, "/v1", ("observability",), deprecated=True),
    )
