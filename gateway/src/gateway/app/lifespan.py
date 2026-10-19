"""Typed application construction and shutdown ownership."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from gateway.app.dependencies import DependencyContainer
from gateway.platform.configuration import GLCPaths
from gateway.platform.networking import OutboundHTTPClient
from gateway.platform.service_registry import load_service_registry
from gateway.platform.startup import StartupCheck, StartupDependencyError, run_startup_checks
from gateway.audit import AuditStore
from gateway.ledger import CallLedger
from gateway.platform.observability import Telemetry
from gateway.llm import LLMService
from typing import TypeVar

T = TypeVar("T")


def _construct(dependency: str, factory: Callable[[], T]) -> T:
    try:
        return factory()
    except BaseException as exc:
        raise StartupDependencyError(dependency, exc) from exc


def build_container(
    *, service_registry_path: Path,
    startup_checks: tuple[StartupCheck, ...] = (),
) -> DependencyContainer:
    """Construct and validate every long-lived dependency before serving."""

    paths = GLCPaths()
    services = load_service_registry(service_registry_path)
    audit = _construct("audit database", lambda: AuditStore(paths.audit_db))
    ledger = _construct("call ledger database", lambda: CallLedger(paths.ledger_db))
    telemetry = Telemetry()
    _construct("telemetry export", telemetry.initialize)
    http = OutboundHTTPClient()
    llm = _construct(
        "LLM service",
        lambda: LLMService.build(
            client=http.client,
            config_dir=paths.config_dir,
            database_path=paths.ledger_db,
            audit=audit,
        ),
    )
    llm.attach_tracer(telemetry.tracer)
    try:
        run_startup_checks(
            (
                StartupCheck("audit database", audit.healthcheck),
                StartupCheck("call ledger database", ledger.healthcheck),
                StartupCheck("telemetry export", telemetry.healthcheck),
                *startup_checks,
            )
        )
    except BaseException:
        telemetry.close()
        raise
    return DependencyContainer(
        service_registry=services,
        http=http,
        audit=audit,
        ledger=ledger,
        telemetry=telemetry,
        llm=llm,
    )


def lifespan_for(
    *,
    service_registry_path: Path,
    startup_checks: tuple[StartupCheck, ...] = (),
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container: DependencyContainer | None = None
        try:
            container = build_container(
                service_registry_path=service_registry_path,
                startup_checks=startup_checks,
            )
            app.state.container = container
            yield
        finally:
            if container is not None:
                await container.close()

    return lifespan
