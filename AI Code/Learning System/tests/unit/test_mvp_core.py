from datetime import date, datetime
from pathlib import Path

import pytest

from study_system.core.baseline import StudyBaseline
from study_system.core.study_core import StudyCore, TemplateCardGenerator
from study_system.repositories.json_repositories import JsonVectorRepository
from study_system.storage.mvp_store import MVPStore
from study_system.types.mvp import ConceptSummary, GeneratedCard, RetrievedContext


class FakeKG:
    def __init__(self) -> None:
        self.concepts = [
            ConceptSummary(id="b", name="Beta", domain="D", summary="Second"),
            ConceptSummary(id="a", name="Alpha", domain="D", summary="First"),
            ConceptSummary(id="c", name="Gamma", domain="D", summary="Third"),
        ]

    def list_concepts(self, limit: int | None = None) -> list[ConceptSummary]:
        result = self.concepts[:]
        return result[:limit] if limit else result

    def get_concept(self, concept_id: str) -> ConceptSummary | None:
        return next((c for c in self.concepts if c.id == concept_id), None)

    def neighborhood(self, concept_id: str, depth: int = 1) -> dict:
        return {"concept_id": concept_id, "depth": depth}

    def search(self, text: str, limit: int = 10) -> list[ConceptSummary]:
        return [c for c in self.concepts if text.lower() in c.name.lower()][:limit]


def baseline(tmp_path: Path) -> StudyBaseline:
    return StudyBaseline(
        daily_card_sets=2,
        cards_per_set=3,
        review_limit=50,
        card_gen_model="test-model",
        feynman_model="test-model",
        challenger_model="test-model",
        prompt_versions={"flashcard": "test_prompt_v1"},
        database_root=tmp_path,
        sqlite_relative_path="study_system.db",
    )


def test_generate_unseen_cards_uses_binary_has_card_gate(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
        generator=TemplateCardGenerator(),
    )

    first = core.generate_unseen_cards()
    assert first["selected_concept_ids"] == ["a", "b"]
    assert first["cards_inserted"] == 6

    second = core.generate_unseen_cards()
    assert second["selected_concept_ids"] == ["c"]
    assert second["cards_inserted"] == 3


def test_rating_updates_review_state_without_review_table(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
        generator=TemplateCardGenerator(),
    )
    core.generate_unseen_cards(temporary_count=1)
    due = core.fetch_due_cards()

    result = core.submit_card_rating(due[0]["id"], 3, now=datetime(2026, 7, 16, 12, 0, 0))

    assert result["rating"] == 3
    assert result["due_at"] is not None
    assert store.table_names() == {
        "cards",
        "review_state",
        "generation_runs",
        "overrides",
    }


def test_feynman_flow_renders_prompt_and_persists_evaluation(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
    )

    started = core.start_feynman("a")
    assert "Explain Alpha" in started["next_prompt"]
    attempt_id = started["attempt_id"]

    graded = core.evaluate_feynman(
        attempt_id,
        "Alpha is the first concept because...",
        conversation_so_far=[{"role": "assistant", "content": "Teach it simply."}],
    )
    assert graded["attempt_id"] == attempt_id
    assert "Alpha is the first concept because..." in graded["grading_prompt"]
    assert "Alpha" in graded["grading_prompt"]  # CANONICAL_NAME substituted
    assert "Teach it simply." in graded["grading_prompt"]

    evaluation = {
        "gaps": [],
        "shallow_areas": [],
        "connections_missed": [],
        "overall_assessment": "solid",
        "ready_to_conclude": True,
    }
    recorded = core.record_feynman_evaluation(attempt_id, evaluation)
    assert recorded["recorded"] is True

    stored = store.connection.execute(
        "SELECT operation FROM generation_runs WHERE id = ?", (recorded["outcome_id"],)
    ).fetchone()
    assert stored["operation"] == "feynman_evaluation"


def test_record_feynman_evaluation_rejects_malformed_shape(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
    )
    attempt_id = core.start_feynman("a")["attempt_id"]
    with pytest.raises(ValueError):
        core.record_feynman_evaluation(attempt_id, {"overall_assessment": "incomplete shape"})


def test_challenger_flow_renders_prompt_and_persists_evaluation(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
    )

    started = core.start_challenger("b")
    assert "Beta" in started["next_prompt"]
    attempt_id = started["attempt_id"]

    graded = core.grade_challenger(attempt_id, "Beta always dominates Alpha.")
    assert "Beta always dominates Alpha." in graded["grading_prompt"]

    evaluation = {
        "initial_probe": "What if the ordering reversed?",
        "follow_up_probes": [],
        "edge_cases": [],
        "known_traps": [],
    }
    recorded = core.record_challenger_evaluation(attempt_id, evaluation)
    assert recorded["recorded"] is True


def test_submit_card_rating_is_idempotent_with_repeated_key(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
        generator=TemplateCardGenerator(),
    )
    core.generate_unseen_cards(temporary_count=1)
    due = core.fetch_due_cards()
    card_id = due[0]["id"]

    first = core.submit_card_rating(
        card_id, 3, now=datetime(2026, 7, 16, 12, 0, 0), idempotency_key="rating-key-1"
    )
    second = core.submit_card_rating(
        card_id, 4, now=datetime(2026, 7, 20, 12, 0, 0), idempotency_key="rating-key-1"
    )

    assert first == second
    row = store.get_card_with_state(card_id)
    assert int(row["reps"]) == 1  # the second (differently-rated) call never actually applied


def test_generate_unseen_cards_is_idempotent_with_repeated_key(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
        generator=TemplateCardGenerator(),
    )

    first = core.generate_unseen_cards(idempotency_key="gen-key-1")
    second = core.generate_unseen_cards(idempotency_key="gen-key-1")

    assert first == second
    # Only the first call's concepts actually got cards; a retried key must
    # not silently re-select and duplicate-generate against fresh concepts.
    assert store.progress_counts()["cards"] == first["cards_inserted"]


def test_submit_card_rating_rejects_unknown_card(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
        generator=TemplateCardGenerator(),
    )
    with pytest.raises(KeyError):
        core.submit_card_rating("does-not-exist", 3)


def test_submit_card_rating_rejects_invalid_rating(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
        generator=TemplateCardGenerator(),
    )
    core.generate_unseen_cards(temporary_count=1)
    card_id = core.fetch_due_cards()[0]["id"]
    with pytest.raises(ValueError):
        core.submit_card_rating(card_id, 99)


def test_fetch_due_cards_filters_by_card_type(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
        generator=TemplateCardGenerator(),
    )
    core.generate_unseen_cards(temporary_count=1)
    flashcard_ids = {c["id"] for c in core.fetch_due_cards()}

    # Insert a non-flashcard card type directly (e.g. a future quiz_mcq card)
    # and confirm the default flashcard-only filter excludes it, matching the
    # documented risk in CLAUDE.md #4 (quiz cards leaking into review).
    store.insert_cards(
        [
            GeneratedCard(
                id="quiz-1",
                concept_id="a",
                front="quiz front",
                back='{"choices": []}',
                card_type="quiz_mcq",
                source_refs=[],
                source_version=None,
                model="test-model",
                prompt_version="test_prompt_v1",
            )
        ]
    )

    default_due = core.fetch_due_cards()
    assert {c["id"] for c in default_due} == flashcard_ids

    unfiltered_due = core.fetch_due_cards(card_types=None)
    assert {c["id"] for c in unfiltered_due} == flashcard_ids | {"quiz-1"}


def test_quality_checker_can_reject_generated_cards(tmp_path: Path) -> None:
    class RejectAllQualityChecker:
        def check(
            self,
            cards: list[GeneratedCard],
            context: RetrievedContext,
            config: StudyBaseline,
        ) -> list[GeneratedCard]:
            del cards, context, config
            return []

    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
        generator=TemplateCardGenerator(),
        quality=RejectAllQualityChecker(),
    )

    result = core.generate_unseen_cards(temporary_count=1)
    assert result["cards_inserted"] == 0
    assert store.progress_counts()["cards"] == 0


def test_set_temporary_override_rejects_value_above_bound(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
    )
    with pytest.raises(ValueError):
        core.set_temporary_override(
            setting="daily_card_sets",
            value=10_000,
            starts_on=date(2026, 7, 16),
            expires_on=date(2026, 7, 30),
            reason="test",
        )


def test_auto_select_practice_is_deterministic_and_keeps_provenance(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
    )

    started = core.start_feynman(idempotency_key="auto-feynman")
    replay = core.start_feynman(idempotency_key="auto-feynman")

    assert started == replay
    assert started["concept_id"] == "a"
    assert started["attempt_id"] == "feynman:a"
    assert started["source_refs"]
    assert store.table_names() == {"cards", "review_state", "generation_runs", "overrides"}


def test_gateway_style_evaluator_is_validated_and_persisted(tmp_path: Path) -> None:
    class FakeEvaluator:
        def evaluate_feynman(self, prompt: str, config: StudyBaseline) -> dict:
            assert "Alpha" in prompt
            return {
                "gaps": [],
                "shallow_areas": [],
                "connections_missed": [],
                "overall_assessment": "grounded",
                "ready_to_conclude": True,
            }

        def grade_challenger(self, prompt: str, config: StudyBaseline) -> dict:
            raise AssertionError("not used")

    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
        practice_evaluator=FakeEvaluator(),
    )
    attempt_id = core.start_feynman("a")["attempt_id"]

    result = core.evaluate_feynman(
        attempt_id, "Alpha is first.", idempotency_key="eval-1"
    )

    assert result["evaluation"]["ready_to_conclude"] is True
    stored = store.connection.execute(
        "SELECT operation, effective_config_json FROM generation_runs WHERE id = ?",
        (result["outcome_id"],),
    ).fetchone()
    assert stored["operation"] == "feynman_evaluation"
    assert "ready_to_conclude" in stored["effective_config_json"]


def test_idempotency_key_cannot_be_reused_across_write_operations(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
    )
    feynman = core.start_feynman("a")
    core.evaluate_feynman(
        feynman["attempt_id"], "Alpha is first.", idempotency_key="shared-key"
    )

    with pytest.raises(ValueError, match="already used"):
        challenger = core.start_challenger("a")
        core.grade_challenger(
            challenger["attempt_id"], "Alpha always wins.", idempotency_key="shared-key"
        )


def test_fourteen_day_override_changes_effective_config_then_expires(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
    )
    core.set_temporary_override(
        setting="daily_card_sets",
        value=7,
        starts_on=date(2026, 7, 16),
        expires_on=date(2026, 7, 29),
        reason="seven sets for fourteen days",
        created_by="agent",
    )

    assert core.effective_config(date(2026, 7, 29)).daily_card_sets == 7
    assert core.effective_config(date(2026, 7, 30)).daily_card_sets == 2


def test_progress_covers_final_kg_unseen_due_activity_and_overrides(tmp_path: Path) -> None:
    store = MVPStore(tmp_path / "study_system.db")
    core = StudyCore(
        baseline=baseline(tmp_path),
        store=store,
        kg=FakeKG(),
        vector=JsonVectorRepository(),
        generator=TemplateCardGenerator(),
    )
    generation = core.generate_unseen_cards(temporary_count=1)
    core.set_temporary_override(
        setting="review_limit",
        value=25,
        starts_on=date.today(),
        expires_on=date.today(),
        reason="one-day chat campaign",
        created_by="user",
    )

    progress = core.progress_counts()

    assert progress["total_concepts"] == 3
    assert progress["concepts_with_cards"] == 1
    assert progress["unseen_concepts"] == 2
    assert progress["due_cards"] == generation["cards_inserted"]
    assert progress["recent_activity"][0]["type"] == "generation_run"
    assert progress["active_overrides"][0]["setting"] == "review_limit"
