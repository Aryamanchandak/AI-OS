# mypy: disable-error-code="no-untyped-def"
"""The HTTP application: startup, bearer-token auth and the `/api/llm/*` routes.

Routes only translate HTTP to `LLMService` calls; the behaviour lives in `service.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
import json
import os
import time
from typing import Annotated, Any, TypeVar, cast

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from gateway import __version__, config
from gateway.budget import DIMENSIONS, BudgetConfigError, parse_principal, period_start
from gateway.ledger import CallLedger
from gateway.models import (
    BudgetSetRequest, ChatRequest, EmbedRequest, PreflightCheck, PreflightRequest, PreflightResponse,
)
from gateway.service import LLMService
from gateway.telemetry import RequestSpans, Telemetry, chat_trace, safe_error

T = TypeVar("T")

API_PREFIX = "/api/llm"
SCHEMA_AND_DOCS_PATHS = frozenset({"/openapi.json", "/docs", "/redoc"})
PREFLIGHT_TIMEOUT_S = 30.0


# --- startup ----------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class StartupCheck:
    """A named check that must pass before the gateway serves requests."""

    dependency: str
    check: Callable[[], None]


class StartupDependencyError(RuntimeError):
    """Startup refused; the message is one JSON line naming the dependency that failed."""

    def __init__(self, dependency: str, cause: BaseException) -> None:
        self.dependency = dependency
        self.cause = cause
        self.event = {
            "event": "gateway.startup.dependency_failed",
            "dependency": dependency,
            "error_type": type(cause).__name__,
            "error": str(cause),
        }
        super().__init__(json.dumps(self.event, sort_keys=True))


def _start(dependency: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except BaseException as exc:
        raise StartupDependencyError(dependency, exc) from exc


def _lifespan(startup_checks: tuple[StartupCheck, ...]) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Build the ledger, telemetry and service, check them, then serve."""
        paths = config.Paths()
        ledger = _start("call ledger database", lambda: CallLedger(paths.ledger_db))
        telemetry = Telemetry()
        _start("telemetry export", telemetry.initialize)
        try:
            llm = _start("LLM service", lambda: LLMService.build(config_dir=paths.config_dir, ledger=ledger))
            llm.tracer = telemetry.tracer
            for check in (
                StartupCheck("call ledger database", ledger.healthcheck),
                StartupCheck("telemetry export", telemetry.healthcheck),
                *startup_checks,
            ):
                _start(check.dependency, check.check)
            app.state.ledger, app.state.telemetry, app.state.llm = ledger, telemetry, llm
            yield
        finally:
            telemetry.close()

    return lifespan


def get_llm_service(request: Request) -> LLMService:
    """The service built at startup. Tests override this dependency with a fake."""
    try:
        return cast(LLMService, request.app.state.llm)
    except AttributeError as exc:
        raise RuntimeError("Gateway service is unavailable before startup") from exc


Service = Annotated[LLMService, Depends(get_llm_service)]


# --- auth -------------------------------------------------------------------

def requires_bearer_token(path: str) -> bool:
    """Protect the API and its schema; only /health stays open."""
    return path.startswith("/api/") or path in SCHEMA_AND_DOCS_PATHS


def _install_bearer_auth(app: FastAPI, expected_token: str) -> None:
    @app.middleware("http")
    async def bearer_auth(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if requires_bearer_token(request.url.path):
            if not expected_token:
                return JSONResponse(status_code=503, content={"detail": "AI_OS_TOKEN is not configured"})
            if request.headers.get("authorization") != f"Bearer {expected_token}":
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)


# --- routes: model calls ----------------------------------------------------

router = APIRouter()


@router.post("/preflight", response_model=PreflightResponse)
async def preflight(request: PreflightRequest, service: Service) -> PreflightResponse:
    # One tiny real chat call and one real embedding call, each reported separately.

    async def probe(kind: str) -> PreflightCheck:
        started = time.perf_counter()
        profile = request.chat_profile if kind == "chat" else request.embedding_profile
        try:
            async with asyncio.timeout(PREFLIGHT_TIMEOUT_S):
                result: dict[str, Any]
                if kind == "chat":
                    result = await service.chat(ChatRequest(
                        prompt="Reply with OK.", profile=profile,
                        provider=request.chat_provider, model=request.chat_model,
                        max_tokens=8, temperature=0, reasoning="off",
                    ))
                else:
                    result = await service.embed(EmbedRequest(text="preflight check", profile=profile))
            return PreflightCheck(
                ok=True, profile=result.get("profile"), provider=result.get("provider"),
                model=result.get("model"), dim=result.get("dim"),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            status = exc.status_code if isinstance(exc, HTTPException) else getattr(exc, "status", None)
            if isinstance(exc, TimeoutError):
                status = 504
            return PreflightCheck(
                ok=False, profile=profile, latency_ms=int((time.perf_counter() - started) * 1000),
                status_code=status,
                error=safe_error(exc.detail if isinstance(exc, HTTPException) else exc) or "probe timed out",
            )

    chat_check, embedding_check = await asyncio.gather(probe("chat"), probe("embedding"))
    return PreflightResponse(ok=chat_check.ok and embedding_check.ok, chat=chat_check, embedding=embedding_check)


@router.post("/chat")
async def chat(request: ChatRequest, service: Service):
    return chat_trace(await service.chat(request))


@router.post("/embed")
async def embed(request: EmbedRequest, service: Service):
    return await service.embed(request)


# --- routes: what is configured ---------------------------------------------

@router.get("/embedders")
async def embedders(service: Service):
    values = {name: provider for name, provider in service.registry.providers.items()
              if provider.capabilities.embeddings}
    return {
        "order": list(values),
        "models": {name: provider.model for name, provider in values.items()},
        "today": await asyncio.to_thread(service.today),
        "profiles": service.profiles.all("embedding"),
    }


@router.get("/providers")
async def providers(service: Service):
    return service.providers()


@router.get("/chat/profiles/{profile}")
async def chat_profile(profile: str, service: Service):
    try:
        return service.profiles.resolve("chat", profile)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/capabilities")
async def capabilities(service: Service):
    return service.capabilities()


@router.get("/status")
async def status(service: Service):
    return service.status()


# --- routes: the call ledger, budgets and prices ----------------------------

@router.get("/calls")
async def calls(service: Service, limit: int = 100, provider: str | None = None, status: str | None = None):
    return await asyncio.to_thread(service.ledger.recent, limit, provider, status)


@router.get("/cost/by_agent")
async def cost_by_agent(service: Service, session: str | None = None, agent: str | None = None):
    return await asyncio.to_thread(lambda: service.ledger.rollup("agent", value=agent, session=session))


@router.get("/budget")
async def list_budgets(service: Service):
    return await asyncio.to_thread(service.budget.describe)


@router.get("/budget/{principal:path}")
async def get_budget(principal: str, service: Service):
    try:
        dimension, value = parse_principal(principal)
    except BudgetConfigError as exc:
        raise HTTPException(400, str(exc)) from exc
    current = await asyncio.to_thread(service.budget.status_for, dimension, value)
    if current is None:
        return {
            "principal": principal, "dimension": dimension, "value": value, "governed": False,
            "limit_usd": None, "spent_usd": 0.0, "spent_lifetime_usd": 0.0,
            "message": "No budget policy matches this principal, so it is unlimited. "
                       "Add one to budgets.yaml or POST /api/llm/budget.",
        }
    policy = service.budget.policy_for(dimension, value)
    assert policy is not None
    return {**current.as_dict(), "governed": True, "policy": policy.as_dict()}


@router.post("/budget")
async def set_budget(request: BudgetSetRequest, service: Service):
    try:
        policy = await asyncio.to_thread(
            service.budget.set_limit, request.principal, request.limit_usd, request.period, request.include_errors)
    except BudgetConfigError as exc:
        raise HTTPException(400, str(exc)) from exc
    current = await asyncio.to_thread(service.budget.status_for, policy.dimension, policy.pattern)
    return {"ok": True, "policy": policy.as_dict(), "status": current.as_dict() if current else None}


@router.delete("/budget/{principal:path}")
async def delete_budget(principal: str, service: Service):
    try:
        removed = await asyncio.to_thread(service.budget.clear_limit, principal)
    except BudgetConfigError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "removed": removed, "principal": principal}


@router.get("/cost/by_principal")
async def cost_by_principal(service: Service, dimension: str | None = None, value: str | None = None,
                            since: float | None = None, period: str = "day", group_by_provider: bool = True):
    start = since if since is not None else period_start(period)
    if dimension:
        if dimension not in DIMENSIONS:
            raise HTTPException(400, f"unknown dimension {dimension!r}; expected one of {list(DIMENSIONS)}")
        rows = await asyncio.to_thread(lambda: service.ledger.rollup(
            dimension, since=start, value=value, group_by_provider=group_by_provider))
        return {"period": period, "since": start, "dimension": dimension, "rows": rows,
                "total_usd": round(sum(row["dollars"] for row in rows), 8)}
    by_dimension = await asyncio.to_thread(
        lambda: {name: service.ledger.rollup(name, since=start) for name in DIMENSIONS})
    return {
        "period": period, "since": start, "dimensions": list(DIMENSIONS), "by_dimension": by_dimension,
        "totals_usd": {name: round(sum(row["dollars"] for row in rows), 8) for name, rows in by_dimension.items()},
    }


@router.get("/pricing")
async def pricing(service: Service, provider: str | None = None, model: str | None = None):
    if not (provider or model):
        return service.pricing.describe()
    price = service.pricing.price_for(provider or "", model)
    return {
        "provider": provider, "model": model,
        "input_usd_per_mtok": price.input_usd_per_mtok, "output_usd_per_mtok": price.output_usd_per_mtok,
        "cache_read_multiplier": price.cache_read_multiplier, "cache_write_multiplier": price.cache_write_multiplier,
        "quality": price.quality, "price_source": price.source, "priced": price.priced,
    }


# --- the application --------------------------------------------------------

def create_app(*, token: str | None = None, startup_checks: tuple[StartupCheck, ...] = ()) -> FastAPI:
    config.load_env()
    expected_token = token if token is not None else os.environ.get("AI_OS_TOKEN", "").strip()
    app = FastAPI(title="AI OS Gateway", version=__version__, lifespan=_lifespan(startup_checks))
    _install_bearer_auth(app, expected_token)
    app.add_middleware(RequestSpans)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router, prefix=API_PREFIX, tags=["llm"])

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
