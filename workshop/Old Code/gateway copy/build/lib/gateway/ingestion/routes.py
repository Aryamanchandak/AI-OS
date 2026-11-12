"""Registration of the ingestion review API."""

from __future__ import annotations

from fastapi import Request

from gateway.app.dependencies import get_container
from gateway.app.router_registry import RouterRegistration
from gateway.ingestion.server import ReviewService, create_router


def _service(request: Request) -> ReviewService:
    return get_container(request).ingestion


def registration() -> RouterRegistration:
    return RouterRegistration(
        router=create_router(_service),
        prefix="/api/ingestion",
        tags=("ingestion",),
    )
