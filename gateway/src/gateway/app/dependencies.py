"""Typed FastAPI dependencies over the lifespan-owned application container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request

from gateway.ledger import CallLedger
from gateway.telemetry import Telemetry
from gateway.llm import LLMService


@dataclass(frozen=True, slots=True)
class DependencyContainer:
    """The complete set of long-lived services owned by this application."""

    ledger: CallLedger
    telemetry: Telemetry
    llm: LLMService

    async def close(self) -> None:
        """Close container-owned resources in reverse construction order."""
        self.telemetry.close()


def get_container(request: Request) -> DependencyContainer:
    """Return the container installed by lifespan, with a typed failure mode."""

    try:
        return cast(DependencyContainer, request.app.state.container)
    except AttributeError as exc:
        raise RuntimeError("Gateway dependencies are unavailable before lifespan startup") from exc


def get_llm_service(
    container: Annotated[DependencyContainer, Depends(get_container)],
) -> LLMService:
    """Expose LLMService only to Gateway's own LLM route module."""

    return container.llm
