"""Gateway ASGI application assembly."""

from __future__ import annotations

import os
from pathlib import Path

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gateway import __version__
from gateway.app.dependencies import get_service_registry
from gateway.app.lifespan import lifespan_for
from gateway.app.middleware import (
    SCHEMA_AND_DOCS_PATHS as SCHEMA_AND_DOCS_PATHS,
    install_bearer_auth,
)
from gateway.app.router_registry import (
    RouterRegistration,
    migrated_domain_registrations,
    register_routers,
)
from gateway.app.temporary_ingestion_adapter import (
    AI_OS_ROOT as AI_OS_ROOT,
    INGESTION_ROOT as INGESTION_ROOT,
    create_review_service,
    ingestion_registration,
)
from gateway.platform.service_registry import ServiceRegistry
from gateway.platform.startup import StartupCheck


GATEWAY_ROOT = AI_OS_ROOT / "gateway"
SHELL_DIST = AI_OS_ROOT / "shell" / "dist"
DEFAULT_GATEWAY_CONFIG = GATEWAY_ROOT / "config" / "gateway.yaml"
DEFAULT_SERVICE_REGISTRY = GATEWAY_ROOT / "config" / "services.yaml"


def _diagnostics_registration() -> RouterRegistration:
    router = APIRouter()

    @router.get("/services")
    def service_diagnostics(
        service_registry: Annotated[ServiceRegistry, Depends(get_service_registry)],
    ) -> dict[str, object]:
        return {"services": service_registry.diagnostics()}

    return RouterRegistration(router=router, prefix="/api/diagnostics", tags=("diagnostics",))


def create_app(
    *,
    token: str | None = None,
    gateway_config_path: Path = DEFAULT_GATEWAY_CONFIG,
    service_registry_path: Path = DEFAULT_SERVICE_REGISTRY,
    startup_checks: tuple[StartupCheck, ...] = (),
) -> FastAPI:
    # cockpit.server.create_router captures a concrete ReviewService. This is
    # the explicitly temporary Plan-06 exception to lifespan construction.
    legacy_review_service = create_review_service()
    expected_token = token if token is not None else os.environ.get("AI_OS_TOKEN", "").strip()
    app = FastAPI(
        title="AI OS Gateway",
        version=__version__,
        lifespan=lifespan_for(
            gateway_config_path=gateway_config_path,
            service_registry_path=service_registry_path,
            legacy_review_service=legacy_review_service,
            startup_checks=startup_checks,
        ),
    )
    install_bearer_auth(app, expected_token)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    register_routers(
        app,
        (
            ingestion_registration(legacy_review_service),
            _diagnostics_registration(),
            *migrated_domain_registrations(),
        ),
    )

    if SHELL_DIST.is_dir():
        assets = SHELL_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{route:path}", include_in_schema=False)
        def shell(route: str) -> FileResponse:
            candidate = SHELL_DIST / route
            if route and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(SHELL_DIST / "index.html")

    return app


app = create_app()
