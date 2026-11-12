"""Gateway ASGI application assembly."""

from __future__ import annotations

import os
from pathlib import Path

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
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
from gateway.ingestion.setup import AI_OS_ROOT as AI_OS_ROOT
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
    service_registry_path: Path | None = None,
    startup_checks: tuple[StartupCheck, ...] = (),
) -> FastAPI:
    expected_token = token if token is not None else os.environ.get("AI_OS_TOKEN", "").strip()
    resolved_registry_path = service_registry_path or Path(
        os.environ.get("AI_OS_SERVICE_REGISTRY_PATH", str(DEFAULT_SERVICE_REGISTRY))
    )
    app = FastAPI(
        title="AI OS Gateway",
        version=__version__,
        lifespan=lifespan_for(
            gateway_config_path=gateway_config_path,
            service_registry_path=resolved_registry_path,
            startup_checks=startup_checks,
        ),
    )
    install_bearer_auth(app, expected_token)
    from gateway.platform.observability.capture import DiagnosticCapture
    app.add_middleware(DiagnosticCapture)

    @app.get("/dashboard", response_class=RedirectResponse)
    def legacy_dashboard() -> RedirectResponse:
        return RedirectResponse("/observability", status_code=307)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/healthz")
    def legacy_healthz(
        service_registry: Annotated[ServiceRegistry, Depends(get_service_registry)],
    ) -> dict[str, object]:
        """Preserve the old JSON health response on Gateway's configured port."""
        return {"ok": True, "port": service_registry.get("gateway").port}

    ingestion, *other_domains = migrated_domain_registrations()
    register_routers(
        app,
        (
            ingestion,
            _diagnostics_registration(),
            *other_domains,
        ),
    )

    # API typos and retired routes must not be mistaken for a successful shell
    # page. These handlers run after the registered API routes and before the
    # shell's navigation fallback.
    @app.api_route(
        "/v1/{route:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    def unknown_legacy_api(route: str) -> None:
        raise HTTPException(status_code=404, detail="Unknown API route")

    @app.api_route(
        "/api/{route:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    def unknown_api(route: str) -> None:
        raise HTTPException(status_code=404, detail="Unknown API route")

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
