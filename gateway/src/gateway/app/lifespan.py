"""Typed application construction and shutdown ownership."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from gateway.app.dependencies import DependencyContainer
from gateway.app.temporary_ingestion_adapter import ReviewService
from gateway.platform.configuration import load_gateway_settings
from gateway.platform.configuration import GLCPaths
from gateway.platform.networking import OutboundHTTPClient
from gateway.platform.service_registry import load_service_registry
from gateway.platform.startup import StartupCheck, StartupDependencyError, run_startup_checks
from gateway.audit import AuditStore
from gateway.control import ControlService
from gateway.policy import PolicyEngine
from gateway.security import PairingStore, RateLimiter
from gateway.ledger import CallLedger
from gateway.platform.observability import Telemetry
from gateway.llm import LLMService
import signal
import sys
from typing import Any, TypeVar

T = TypeVar("T")


def _reload_policy_on_sighup(container: DependencyContainer) -> None:
    """SIGHUP handler body: policy reload only, no other I/O.

    Runs on the main thread inside the interpreter's signal-check point,
    which can interrupt arbitrary code. It must not touch SQLite (the audit
    or pairing stores) or otherwise block; a failed reload is caught and
    logged rather than left to propagate out of the handler, matching GLC's
    original behavior. Unlike the authenticated HTTP reload endpoint
    (`POST /v1/control/reload-policy`), a SIGHUP reload is not audited —
    auditing it would mean doing a database write from the signal frame,
    which this handler deliberately avoids.
    """
    try:
        container.policy.reload()
        print("[gateway] policy.yaml reloaded via SIGHUP", file=sys.stderr)
    except Exception as exc:
        print(f"[gateway] SIGHUP policy reload failed: {exc!r}", file=sys.stderr)


def _construct(dependency: str, factory: Callable[[], T]) -> T:
    try:
        return factory()
    except BaseException as exc:
        raise StartupDependencyError(dependency, exc) from exc


def build_container(
    *, gateway_config_path: Path, service_registry_path: Path,
    startup_checks: tuple[StartupCheck, ...] = (),
) -> DependencyContainer:
    """Construct and validate every long-lived dependency before serving."""

    paths = GLCPaths()
    policy = _construct("policy.yaml", lambda: PolicyEngine.from_yaml(paths.policy))
    audit = _construct("audit database", lambda: AuditStore(paths.audit_db))
    pairings = _construct("pairing database", lambda: PairingStore(paths.pairing_db))
    ledger = _construct("call ledger database", lambda: CallLedger(paths.ledger_db))
    telemetry = Telemetry()
    _construct("telemetry export", telemetry.initialize)
    rate_limiter = RateLimiter()
    channels = _construct("channels.yaml", lambda: paths.load_mapping(paths.channels))
    _construct("channels.yaml", lambda: rate_limiter.configure(channels))
    control = ControlService(
        install_token=_construct("install token", paths.get_or_create_install_token),
        pairings=pairings,
        policy=policy,
        audit=audit,
    )
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
    try:
        run_startup_checks(
            (
                StartupCheck("policy.yaml", policy.healthcheck),
                StartupCheck("audit database", audit.healthcheck),
                StartupCheck("pairing database", pairings.healthcheck),
                StartupCheck("call ledger database", ledger.healthcheck),
                StartupCheck("telemetry export", telemetry.healthcheck),
                *startup_checks,
            )
        )
    except BaseException:
        telemetry.close()
        raise
    return DependencyContainer(
        settings=load_gateway_settings(gateway_config_path),
        service_registry=load_service_registry(service_registry_path),
        http=http,
        policy=policy,
        audit=audit,
        pairings=pairings,
        rate_limiter=rate_limiter,
        ledger=ledger,
        telemetry=telemetry,
        control=control,
        llm=llm,
    )


def lifespan_for(
    *,
    gateway_config_path: Path,
    service_registry_path: Path,
    legacy_review_service: ReviewService,
    startup_checks: tuple[StartupCheck, ...] = (),
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container: DependencyContainer | None = None
        previous_sighup: Any = None
        try:
            container = build_container(
                gateway_config_path=gateway_config_path,
                service_registry_path=service_registry_path,
                startup_checks=startup_checks,
            )
            app.state.container = container
            if hasattr(signal, "SIGHUP"):
                try:
                    previous_sighup = signal.getsignal(signal.SIGHUP)
                    signal.signal(
                        signal.SIGHUP,
                        lambda _signum, _frame: _reload_policy_on_sighup(container),
                    )
                except ValueError:
                    pass
            yield
        finally:
            if previous_sighup is not None and hasattr(signal, "SIGHUP"):
                try:
                    signal.signal(signal.SIGHUP, previous_sighup)
                except ValueError:
                    pass
            if container is not None:
                await container.close()
            # This is the temporary Plan-06 exception: cockpit.server's
            # frozen router factory captures this eagerly-built service.
            legacy_review_service.close()

    return lifespan
