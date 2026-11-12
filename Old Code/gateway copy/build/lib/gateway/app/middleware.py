"""Cross-cutting HTTP middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response


SCHEMA_AND_DOCS_PATHS = frozenset({"/openapi.json", "/docs", "/redoc"})


def requires_bearer_token(path: str) -> bool:
    """Protect internal APIs and their schema while leaving the shell open."""

    return path.startswith("/api/") or path in SCHEMA_AND_DOCS_PATHS


def install_bearer_auth(app: FastAPI, expected_token: str) -> None:
    @app.middleware("http")
    async def bearer_auth(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if requires_bearer_token(request.url.path):
            if not expected_token:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "AI_OS_TOKEN is not configured"},
                )
            if request.headers.get("authorization") != f"Bearer {expected_token}":
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)
