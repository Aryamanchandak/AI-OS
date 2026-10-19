"""Typed FastAPI dependencies over the lifespan-owned application container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request

from gateway.platform.service_registry import ServiceRegistry
from gateway.audit import AuditStore
from gateway.platform.networking import OutboundHTTPClient
from gateway.ledger import CallLedger
from gateway.platform.observability import Telemetry
from gateway.llm import LLMService


@dataclass(frozen=True, slots=True)
class DependencyContainer:
    """The complete set of long-lived services owned by this application."""

    service_registry: ServiceRegistry
    http: OutboundHTTPClient
    audit: AuditStore
    ledger: CallLedger
    telemetry: Telemetry
    llm: LLMService

    async def close(self) -> None:
        """Close container-owned resources in reverse construction order."""
        self.telemetry.close()
        await self.http.close()


def get_container(request: Request) -> DependencyContainer:
    """Return the container installed by lifespan, with a typed failure mode."""

    try:
        return cast(DependencyContainer, request.app.state.container)
    except AttributeError as exc:
        raise RuntimeError("Gateway dependencies are unavailable before lifespan startup") from exc


def get_service_registry(
    container: Annotated[DependencyContainer, Depends(get_container)],
) -> ServiceRegistry:
    """Provide the service registry to routes without untyped state access."""

    return container.service_registry


def get_llm_service(
    container: Annotated[DependencyContainer, Depends(get_container)],
) -> LLMService:
    """Expose LLMService only to Gateway's own LLM route module."""

    return container.llm
