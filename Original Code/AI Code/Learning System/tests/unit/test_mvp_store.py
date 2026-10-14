from datetime import date, datetime
from pathlib import Path
import sqlite3

import pytest

from study_system.core.baseline import StudyBaseline, merge_overrides
from study_system.storage.mvp_store import MVPStore
from study_system.types.card import FSRSState
from study_system.types.mvp import GeneratedCard


def test_mvp_store_has_expected_study_tables(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    assert store.table_names() == {
        "cards",
        "review_state",
        "generation_runs",
        "overrides",
    }


def test_prototype_auxiliary_tables_are_preserved_then_removed(tmp_path: Path) -> None:
    db_path = tmp_path / "study_system.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE idempotency_keys (
            key TEXT PRIMARY KEY, tool TEXT NOT NULL, result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE practice_attempts (
            id TEXT PRIMARY KEY, mode TEXT NOT NULL, concept_id TEXT NOT NULL,
            student_input TEXT, grading_prompt TEXT, evaluation_json TEXT,
            source_refs_json TEXT NOT NULL DEFAULT '[]', model TEXT,
            prompt_version TEXT, created_at TEXT NOT NULL, evaluated_at TEXT
        );
        INSERT INTO idempotency_keys VALUES
            ('retry-1', 'submit_card_rating', '{"ok": true}', '2026-07-16T10:00:00');
        INSERT INTO practice_attempts VALUES
            ('legacy-outcome', 'feynman', 'concept-1', 'answer', 'prompt',
             '{"ready_to_conclude": true}', '[]', 'model', 'v1',
             '2026-07-16T10:00:00', '2026-07-16T10:01:00');
        """
    )
    conn.close()

    store = MVPStore(db_path)

    assert store.table_names() == {"cards", "review_state", "generation_runs", "overrides"}
    assert store.get_idempotent_result("retry-1", "submit_card_rating") == {"ok": True}
    practice = store.connection.execute(
        "SELECT operation, effective_config_json FROM generation_runs WHERE id='legacy-outcome'"
    ).fetchone()
    assert practice["operation"] == "feynman_evaluation"
    assert "ready_to_conclude" in practice["effective_config_json"]


def test_active_overrides_are_time_bounded_and_cancellable(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    active_id = store.create_override(
        setting="daily_card_sets",
        value=7,
        starts_on=date(2026, 7, 15),
        expires_on=date(2026, 7, 28),
        reason="test",
        created_by="pytest",
    )
    store.create_override(
        setting="cards_per_set",
        value=2,
        starts_on=date(2026, 8, 1),
        expires_on=date(2026, 8, 7),
        reason="future",
        created_by="pytest",
    )

    assert store.active_overrides(date(2026, 7, 16)) == {"daily_card_sets": 7}
    assert store.cancel_override(active_id) is True
    assert store.active_overrides(date(2026, 7, 16)) == {}


def test_store_idempotency_result_round_trips(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    assert store.get_idempotent_result("k1") is None

    store.save_idempotent_result("k1", "some_tool", {"outcome": "success"})
    assert store.get_idempotent_result("k1") == {"outcome": "success"}

    # Saving again under the same key must not overwrite (first write wins).
    store.save_idempotent_result("k1", "some_tool", {"outcome": "different"})
    assert store.get_idempotent_result("k1") == {"outcome": "success"}


def test_merge_overrides_enforces_configured_max_bound() -> None:
    baseline = StudyBaseline(
        daily_card_sets=5,
        cards_per_set=5,
        review_limit=50,
        card_gen_model="gpt-4o-mini",
        feynman_model="gpt-4o-mini",
        challenger_model="gpt-4o-mini",
        prompt_versions={},
        database_root=Path("/tmp/db"),
        sqlite_relative_path="Ingested/SQLite/study_system/study_system.db",
        override_max_values={"daily_card_sets": 7},
    )

    assert merge_overrides(baseline, {"daily_card_sets": 7}).daily_card_sets == 7
    with pytest.raises(ValueError):
        merge_overrides(baseline, {"daily_card_sets": 8})


def test_merge_overrides_validates_allowed_settings() -> None:
    baseline = StudyBaseline(
        daily_card_sets=5,
        cards_per_set=5,
        review_limit=50,
        card_gen_model="gpt-4o-mini",
        feynman_model="gpt-4o-mini",
        challenger_model="gpt-4o-mini",
        prompt_versions={},
        database_root=Path("/tmp/db"),
        sqlite_relative_path="Ingested/SQLite/study_system/study_system.db",
    )

    effective = merge_overrides(baseline, {"daily_card_sets": 9})
    assert effective.daily_card_sets == 9
    assert baseline.daily_card_sets == 5

    with pytest.raises(ValueError):
        merge_overrides(baseline, {"topic_overrides": ["ethics"]})

    for protected_setting in (
        "database_root",
        "kg_concepts_path",
        "vector_snippets_path",
        "card_gen_model",
        "prompt_versions",
    ):
        with pytest.raises(ValueError):
            merge_overrides(baseline, {protected_setting: "not-allowed"})


def test_recent_activity_unifies_generation_review_and_practice(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    card = GeneratedCard(
        id="card-1",
        concept_id="concept-1",
        front="What is duration?",
        back="Interest-rate sensitivity.",
        card_type="flashcard",
        source_refs=[{"type": "kg_concept", "id": "concept-1"}],
        source_version="v1",
        model="test",
        prompt_version="test-v1",
    )
    store.insert_cards([card])
    run_id = store.start_generation_run(
        effective_config_json="{}", selected_concept_ids=["concept-1"]
    )
    store.finish_generation_run(run_id, "success")
    reviewed_at = datetime(2026, 7, 16, 12, 0, 0)
    store.update_review_state(
        "card-1",
        FSRSState(
            stability=1.0,
            difficulty=5.0,
            elapsed_days=0,
            scheduled_days=1,
            reps=1,
            lapses=0,
            state="learning",
        ),
        reviewed_at=reviewed_at,
        evidence={"last_rating": 3},
    )
    outcome_id = store.record_practice_outcome(
        mode="feynman",
        concept_id="concept-1",
        student_input="Duration measures price sensitivity.",
        grading_prompt="Evaluate the explanation.",
        evaluation={"ready_to_conclude": True},
        source_refs=[{"type": "kg_concept", "id": "concept-1"}],
        model="test",
        prompt_version="feynman-v1",
    )

    activity = store.recent_activity()

    assert {item["type"] for item in activity} == {
        "generation_run",
        "card_review",
        "feynman_evaluated",
    }
    review = next(item for item in activity if item["type"] == "card_review")
    assert review["details"]["evidence"]["last_rating"] == 3
    assert any(item["entity_id"] == outcome_id for item in activity)

    with pytest.raises(ValueError):
        store.recent_activity(limit=0)
