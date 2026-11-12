"""Typed FastAPI dependencies over the lifespan-owned application container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request

from gateway.platform.configuration import GatewaySettings
from gateway.platform.service_registry import ServiceRegistry
from gateway.audit import AuditStore
from gateway.control import ControlService
from gateway.platform.networking import OutboundHTTPClient
from gateway.policy import PolicyEngine
from gateway.security import PairingStore, RateLimiter
from gateway.ledger import CallLedger
from gateway.platform.observability import Telemetry
from gateway.llm import LLMService
from gateway.channels.service import ChannelService
from gateway.ingestion.server import ReviewService
from gateway.ingestion.http_client import configure_gateway_url


@dataclass(frozen=True, slots=True)
class DependencyContainer:
    """The complete set of long-lived services owned by this application."""

    settings: GatewaySettings
    service_registry: ServiceRegistry
    http: OutboundHTTPClient
    policy: PolicyEngine
    audit: AuditStore
    pairings: PairingStore
    rate_limiter: RateLimiter
    ledger: CallLedger
    telemetry: Telemetry
    control: ControlService
    llm: LLMService
    channels: ChannelService
    ingestion: ReviewService

    async def close(self) -> None:
        """Close container-owned resources in reverse construction order.

        Plan 02 has no non-legacy closeable resource yet. This method makes
        shutdown ownership explicit before Plans 04–06 add async clients and
        connection pools.
        """
        self.ingestion.close()
        configure_gateway_url(None)
        await self.channels.close()
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


def get_control_service(
    container: Annotated[DependencyContainer, Depends(get_container)],
) -> ControlService:
    return container.control


def get_llm_service(
    container: Annotated[DependencyContainer, Depends(get_container)],
) -> LLMService:
    """Expose LLMService only to Gateway's own LLM route module."""

    return container.llm


def get_channel_service(
    container: Annotated[DependencyContainer, Depends(get_container)],
) -> ChannelService:
    return container.channels


def get_ingestion_service(
    container: Annotated[DependencyContainer, Depends(get_container)],
) -> ReviewService:
    return container.ingestion
