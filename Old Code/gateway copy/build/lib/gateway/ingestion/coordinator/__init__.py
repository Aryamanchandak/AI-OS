"""Public repository-level sequential coordinator API."""

from __future__ import annotations

from pathlib import Path

from gateway.ingestion.config import IngestionConfig, IntakeConfig
from gateway.ingestion.coordinator.coordinator import RunCoordinator
from gateway.ingestion.coordinator.errors import (
    GateUnavailable,
    IllegalDecisionError,
    IllegalStageTransition,
    NoActiveRunError,
    PreflightFailed,
    RunBusyError,
)
from gateway.ingestion.coordinator.report import RunReportView, read_report
from gateway.ingestion.coordinator.stages import (
    LEGAL_TRANSITIONS,
    RunStage,
    StageStatus,
    assert_transition,
)
from gateway.ingestion.coordinator.state import (
    DecisionRequest,
    ErrorView,
    PendingDecision,
    ProgressView,
    RunView,
    StageView,
)


_ACTIVE: dict[Path, RunCoordinator] = {}


def _key(config: IngestionConfig) -> Path:
    return Path(config.coordinator_db_path).expanduser().resolve()


def _active(config: IngestionConfig) -> RunCoordinator:
    try:
        return _ACTIVE[_key(config)]
    except KeyError as error:
        raise NoActiveRunError(
            "no active coordinator run; call start_run first"
        ) from error


def start_run(config: IngestionConfig, *, resolver: str) -> RunView:
    """Start the only supported full repository run and advance until blocked."""

    key = _key(config)
    existing = _ACTIVE.pop(key, None)
    if existing is not None and existing.terminal_result is None:
        _ACTIVE[key] = existing
        raise RunBusyError("a repository run is already active in this process")
    if existing is not None:
        # A finished run — complete or failed — is replaced rather than
        # refused. Release its lock *before* constructing the new coordinator,
        # whose state store acquires that same lock on the way up.
        existing.close()
    coordinator = RunCoordinator(config, resolver=resolver)
    _ACTIVE[key] = coordinator
    return coordinator.advance()


def advance(config: IngestionConfig) -> RunView:
    """Advance the active run until it blocks, fails, or completes."""

    return _active(config).advance()


def submit_decision(config: IngestionConfig, decision: DecisionRequest) -> RunView:
    """Persist exactly one matching human decision and continue."""

    return _active(config).submit_decision(decision)


def retry(config: IngestionConfig) -> RunView:
    """Retry the exact stage that failed."""

    return _active(config).retry()


def run_report(
    config: IngestionConfig, run_id: str | None = None
) -> RunReportView:
    """Read a completed run report, defaulting to the newest one."""

    return read_report(config.database_root / "reports", run_id)


__all__ = [
    "DecisionRequest",
    "ErrorView",
    "GateUnavailable",
    "IllegalDecisionError",
    "IllegalStageTransition",
    "IngestionConfig",
    "IntakeConfig",
    "LEGAL_TRANSITIONS",
    "NoActiveRunError",
    "PendingDecision",
    "PreflightFailed",
    "ProgressView",
    "RunBusyError",
    "RunCoordinator",
    "RunReportView",
    "RunStage",
    "RunView",
    "StageStatus",
    "StageView",
    "advance",
    "assert_transition",
    "retry",
    "run_report",
    "start_run",
    "submit_decision",
]
