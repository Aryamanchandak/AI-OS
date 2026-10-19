"""Gateway ASGI application assembly."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from gateway import __version__, env
from gateway.app.lifespan import lifespan_for
from gateway.app.middleware import (
    SCHEMA_AND_DOCS_PATHS as SCHEMA_AND_DOCS_PATHS,
    install_bearer_auth,
)
from gateway.app.router_registry import (
    migrated_domain_registrations,
    register_routers,
)
from gateway.platform.configuration.glc import AI_OS_ROOT as AI_OS_ROOT
from gateway.platform.startup import StartupCheck


def create_app(
    *,
    token: str | None = None,
    startup_checks: tuple[StartupCheck, ...] = (),
) -> FastAPI:
    env.load_env()
    expected_token = token if token is not None else os.environ.get("AI_OS_TOKEN", "").strip()
    app = FastAPI(
        title="AI OS Gateway",
        version=__version__,
        lifespan=lifespan_for(startup_checks=startup_checks),
    )
    install_bearer_auth(app, expected_token)
    from gateway.platform.observability.capture import DiagnosticCapture
    app.add_middleware(DiagnosticCapture)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    register_routers(app, migrated_domain_registrations())

    # Unknown API paths get an explicit JSON 404 after the registered routes.
    @app.api_route(
        "/api/{route:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    def unknown_api(route: str) -> None:
        raise HTTPException(status_code=404, detail="Unknown API route")

    return app


app = create_app()
