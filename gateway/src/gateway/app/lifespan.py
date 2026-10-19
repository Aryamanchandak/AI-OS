"""Typed application construction and shutdown ownership."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from gateway.app.dependencies import DependencyContainer
from gateway.platform.configuration import GLCPaths
from gateway.platform.startup import StartupCheck, StartupDependencyError, run_startup_checks
from gateway.ledger import CallLedger
from gateway.telemetry import Telemetry
from gateway.llm import LLMService
from typing import TypeVar

T = TypeVar("T")


def _construct(dependency: str, factory: Callable[[], T]) -> T:
    try:
        return factory()
    except BaseException as exc:
        raise StartupDependencyError(dependency, exc) from exc


def build_container(
    *, startup_checks: tuple[StartupCheck, ...] = (),
) -> DependencyContainer:
    """Construct and validate every long-lived dependency before serving."""

    paths = GLCPaths()
    ledger = _construct("call ledger database", lambda: CallLedger(paths.ledger_db))
    telemetry = Telemetry()
    _construct("telemetry export", telemetry.initialize)
    llm = _construct(
        "LLM service",
        lambda: LLMService.build(
            config_dir=paths.config_dir,
            ledger=ledger,
        ),
    )
    llm.attach_tracer(telemetry.tracer)
    try:
        run_startup_checks(
            (
                StartupCheck("call ledger database", ledger.healthcheck),
                StartupCheck("telemetry export", telemetry.healthcheck),
                *startup_checks,
            )
        )
    except BaseException:
        telemetry.close()
        raise
    return DependencyContainer(
        ledger=ledger,
        telemetry=telemetry,
        llm=llm,
    )


def lifespan_for(
    *,
    startup_checks: tuple[StartupCheck, ...] = (),
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container: DependencyContainer | None = None
        try:
            container = build_container(startup_checks=startup_checks)
            app.state.container = container
            yield
        finally:
            if container is not None:
                await container.close()

    return lifespan
