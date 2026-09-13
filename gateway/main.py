from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
import os
from pathlib import Path
import sys

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response


# The gateway, shell, and ingestion pipeline are siblings under the AI OS root.
# Keeping this relationship explicit makes the local application easy to run
# without installing the ingestion package separately.
AI_OS_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = AI_OS_ROOT / "ingestion-pipeline" / "merged-ingestion"
SHELL_DIST = AI_OS_ROOT / "shell" / "dist"

# FastAPI's own schema and documentation routes. They are not under /api/ but
# they publish the internal API description, so they carry the same guard.
# Note: with /openapi.json protected, the Swagger and ReDoc pages render but
# cannot self-load the schema, because a query-string token is deliberately not
# offered as a second authentication mechanism.
SCHEMA_AND_DOCS_PATHS = frozenset({"/openapi.json", "/docs", "/redoc"})

for import_root in (INGESTION_ROOT / "src", INGESTION_ROOT):
    value = str(import_root)
    if value not in sys.path:
        sys.path.insert(0, value)

from cockpit.server import ReviewService, config_from_environment, create_router  # noqa: E402


def _service() -> ReviewService:
    if os.environ.get("AI_OS_PREVIEW", "").strip() == "1":
        from preview import PreviewCoordinator, preview_config

        return ReviewService(
            preview_config(), resolver="preview-reviewer", coordinator_api=PreviewCoordinator()
        )

    # The ingestion package can still be configured explicitly, but the local
    # AI OS layout should work without remembering another environment value.
    os.environ.setdefault("INGESTION_DATABASE_ROOT", str(AI_OS_ROOT / "Database"))
    return ReviewService(
        config_from_environment(),
        resolver=os.environ.get("INGESTION_RESOLVER", "local-reviewer"),
    )


def create_app(*, token: str | None = None) -> FastAPI:
    service = _service()
    expected_token = token if token is not None else os.environ.get("AI_OS_TOKEN", "").strip()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        service.close()

    app = FastAPI(title="AI OS Gateway", version="0.1.0", lifespan=lifespan)
    app.state.review_service = service

    def _requires_token(path: str) -> bool:
        """Every internal route except /health needs the bearer token.

        The schema and documentation routes describe the internal API just as
        completely as the API itself, so they are protected identically. Static
        shell routes stay open: the shell has to load before it can ask for a
        token.
        """

        return path.startswith("/api/") or path in SCHEMA_AND_DOCS_PATHS

    @app.middleware("http")
    async def bearer_auth(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if _requires_token(request.url.path):
            if not expected_token:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "AI_OS_TOKEN is not configured"},
                )
            if request.headers.get("authorization") != f"Bearer {expected_token}":
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(create_router(service), prefix="/api/ingestion", tags=["ingestion"])

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
