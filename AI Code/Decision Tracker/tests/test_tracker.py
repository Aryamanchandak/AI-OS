import json
import sqlite3
from datetime import date, timedelta

import pytest

from decision_tracker.models import (
    BaseRate,
    Claim,
    DecisionClass,
    DecisionDraft,
    Reasoning,
    ResolutionInput,
    SourceClassification,
)
from decision_tracker.service import DecisionTracker, DecisionTrackerError


def forecast_draft(
    *,
    classification: SourceClassification = SourceClassification.PUBLIC,
    falsifiers: list[str] | None = None,
) -> DecisionDraft:
    return DecisionDraft(
        author="AC2",
        **{"class": DecisionClass.FORECAST},
        source_classification=classification,
        title="A falsifiable forecast",
        domain=["rates"],
        claim=Claim(
            statement="The event occurs",
            resolution_source="public series close",
            resolution_date=date.today() + timedelta(days=30),
            probability=0.7,
        ),
        reasoning=Reasoning(
            base_rate=BaseRate(value=0.5, source="historical sample"),
            falsifiers=falsifiers if falsifiers is not None else ["opposite public print"],
        ),
    )


@pytest.fixture
def tracker(tmp_path) -> DecisionTracker:
    return DecisionTracker(tmp_path / "tracker.db")


def test_full_forecast_lifecycle_scores_and_verifies(tracker: DecisionTracker) -> None:
    draft = tracker.log(forecast_draft())
    assert draft.id.startswith("DR-")
    assert draft.status.value == "DRAFT"

    live = tracker.commit(draft.id)
    assert live.status.value == "LIVE"
    assert live.integrity.commit_hash

    resolved = tracker.resolve(
        draft.id,
        ResolutionInput(
            outcome=True,
            evidence="Published close",
            resolver_source="manual:public series",
            automated=True,
        ),
    )
    assert resolved.status.value == "RESOLVED"
    assert resolved.resolution is not None
    assert resolved.resolution.brier == pytest.approx(0.09)
    assert resolved.resolution.skill_vs_base_rate == pytest.approx(0.64)
    assert [event.event_type for event in tracker.store.events(draft.id)] == [
        "DRAFT_CREATED",
        "COMMITTED",
        "ACTIVATED",
        "RESOLVED",
    ]
    assert tracker.store.verify() == (True, "integrity verified")


def test_blocked_source_creates_no_database_event(tracker: DecisionTracker) -> None:
    with pytest.raises(DecisionTrackerError, match="cannot be persisted"):
        tracker.log(forecast_draft(classification=SourceClassification.BLOCKED))

    assert tracker.store.events() == []
    assert tracker.store.list() == []


def test_admission_gate_refuses_missing_falsifier(tracker: DecisionTracker) -> None:
    draft = tracker.log(forecast_draft(falsifiers=[]))

    with pytest.raises(DecisionTrackerError, match="falsifier"):
        tracker.commit(draft.id)

    assert tracker.require(draft.id).status.value == "DRAFT"


def test_forecast_resolution_requires_provenance(tracker: DecisionTracker) -> None:
    draft = tracker.log(forecast_draft())
    tracker.commit(draft.id)

    with pytest.raises(DecisionTrackerError, match="automated resolver"):
        tracker.resolve(
            draft.id,
            ResolutionInput(outcome=True, evidence="Published close"),
        )


def test_non_forecast_can_resolve_manually_without_binary_score(tracker: DecisionTracker) -> None:
    draft_data = forecast_draft().model_dump(by_alias=True)
    draft_data["class"] = "BUILD"
    draft_data["claim"]["probability"] = None
    draft_data["claim"]["success_metric"] = "Migration completes without data loss"
    draft = tracker.log(DecisionDraft.model_validate(draft_data))
    tracker.commit(draft.id)

    resolved = tracker.resolve(
        draft.id,
        ResolutionInput(outcome="completed", evidence="Acceptance test passed"),
    )

    assert resolved.resolution is not None
    assert resolved.resolution.brier is None


def test_projection_is_rebuildable_from_events(tracker: DecisionTracker) -> None:
    first = tracker.log(forecast_draft())
    tracker.commit(first.id)

    with tracker.store.connect() as connection:
        connection.execute("DELETE FROM decisions")
        connection.commit()
    assert tracker.store.list() == []

    assert tracker.rebuild_projection() == 1
    assert tracker.require(first.id).status.value == "LIVE"


def test_event_table_rejects_mutation(tracker: DecisionTracker) -> None:
    tracker.log(forecast_draft())

    with tracker.store.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM events")


def test_integrity_check_detects_projection_independent_event_tampering(
    tracker: DecisionTracker,
) -> None:
    draft = tracker.log(forecast_draft())
    tracker.commit(draft.id)

    with tracker.store.connect() as connection:
        connection.execute("DROP TRIGGER events_no_update")
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE sequence = 1",
            (json.dumps({"tampered": True}),),
        )
        connection.commit()

    valid, message = tracker.store.verify()
    assert valid is False
    assert "event chain failed" in message
