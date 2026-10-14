from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from ingestion.coordinator.errors import IllegalStageTransition


class RunStage(StrEnum):
    CREATED = "created"
    PREFLIGHT = "preflight"
    DISCOVER_INTAKE = "discover_intake"
    INTAKE_ITEM = "intake_item"
    INTAKE_BARRIER = "intake_barrier"
    CAPTURE_OBSIDIAN = "capture_obsidian"
    PROCESS_PENDING = "process_pending"
    PROPOSAL_REVIEW = "proposal_review"
    DISPATCH_RETRY = "dispatch_retry"
    COMPLETE = "complete"
    FAILED = "failed"


class StageStatus(StrEnum):
    RUNNING = "running"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    DONE = "done"
    FAILED = "failed"


LEGAL_TRANSITIONS: Mapping[RunStage, frozenset[RunStage]] = {
    RunStage.CREATED: frozenset({RunStage.PREFLIGHT}),
    RunStage.PREFLIGHT: frozenset({RunStage.DISCOVER_INTAKE, RunStage.FAILED}),
    RunStage.DISCOVER_INTAKE: frozenset(
        {RunStage.INTAKE_ITEM, RunStage.INTAKE_BARRIER, RunStage.FAILED}
    ),
    RunStage.INTAKE_ITEM: frozenset(
        {RunStage.INTAKE_ITEM, RunStage.INTAKE_BARRIER, RunStage.FAILED}
    ),
    RunStage.INTAKE_BARRIER: frozenset(
        {RunStage.CAPTURE_OBSIDIAN, RunStage.COMPLETE, RunStage.FAILED}
    ),
    RunStage.CAPTURE_OBSIDIAN: frozenset(
        {RunStage.PROCESS_PENDING, RunStage.FAILED}
    ),
    RunStage.PROCESS_PENDING: frozenset(
        {RunStage.PROPOSAL_REVIEW, RunStage.DISPATCH_RETRY, RunStage.FAILED}
    ),
    RunStage.PROPOSAL_REVIEW: frozenset(
        {RunStage.PROPOSAL_REVIEW, RunStage.DISPATCH_RETRY, RunStage.FAILED}
    ),
    RunStage.DISPATCH_RETRY: frozenset({RunStage.COMPLETE, RunStage.FAILED}),
    RunStage.COMPLETE: frozenset(),
    RunStage.FAILED: frozenset(
        {
            RunStage.PREFLIGHT,
            RunStage.DISCOVER_INTAKE,
            RunStage.INTAKE_ITEM,
            RunStage.INTAKE_BARRIER,
            RunStage.CAPTURE_OBSIDIAN,
            RunStage.PROCESS_PENDING,
            RunStage.PROPOSAL_REVIEW,
            RunStage.DISPATCH_RETRY,
        }
    ),
}


def assert_transition(current: RunStage, target: RunStage) -> None:
    if target not in LEGAL_TRANSITIONS[current]:
        raise IllegalStageTransition(
            f"{current.value} -> {target.value} is not a legal run transition"
        )
