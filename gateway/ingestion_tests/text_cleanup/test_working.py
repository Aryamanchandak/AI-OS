from __future__ import annotations

import pytest

from gateway.ingestion.text_cleanup.abbreviations import MappingRow, find_candidates
from gateway.ingestion.text_cleanup.models import Passage
from gateway.ingestion.text_cleanup.working import IllegalCleanupAction, WorkingState


def make_state(text: str = "w/ one w/ two") -> WorkingState:
    passages = [Passage(index=0, text=text)]
    candidates = find_candidates(passages, [MappingRow("m1", "w/", "with", True)])
    return WorkingState(
        content_hash="hash1",
        source_kind="text_file",
        abbreviation_base_passages=tuple(passages),
        abbreviation_candidates=tuple(candidates),
    )


def test_starts_on_first_abbreviation_occurrence() -> None:
    state = make_state()
    view = state.current_view()
    assert view is not None
    assert view.candidate.ordinal == 1
    assert view.total == 2


def test_navigate_next_and_previous_change_only_displayed_occurrence() -> None:
    state = make_state()
    first_text = state.working_passages()[0].text
    state.navigate("next")
    assert state.interaction_revision == 1
    assert state.working_draft_revision == 0
    assert state.current_view().candidate.ordinal == 2
    assert state.working_passages()[0].text == first_text
    state.navigate("previous")
    assert state.current_view().candidate.ordinal == 1


def test_navigate_clamps_at_boundaries() -> None:
    state = make_state()
    state.navigate("previous")
    assert state.current_view().candidate.ordinal == 1
    state.navigate("next")
    state.navigate("next")
    state.navigate("next")
    assert state.current_view().candidate.ordinal == 2


def test_decide_apply_once_resolves_and_bumps_both_revisions() -> None:
    state = make_state()
    occurrence_id = state.abbreviation_candidates[0].occurrence_id
    before, after = state.decide(occurrence_id, "apply_once")
    assert before == "w/"
    assert after == "with"
    assert state.interaction_revision == 1
    assert state.working_draft_revision == 1
    assert state.working_passages()[0].text.startswith("with one")


def test_decide_skip_leaves_text_unchanged_but_still_resolves() -> None:
    state = make_state()
    occurrence_id = state.abbreviation_candidates[0].occurrence_id
    state.decide(occurrence_id, "skip")
    assert state.working_passages()[0].text == "w/ one w/ two"
    assert state.interaction_revision == 1
    assert state.working_draft_revision == 0
    assert state.is_phase_settled("abbreviation") is False  # second occurrence undecided


def test_decide_unknown_occurrence_raises() -> None:
    state = make_state()
    with pytest.raises(IllegalCleanupAction):
        state.decide("not-a-real-id", "apply_once")


def test_decide_wrong_action_for_phase_raises() -> None:
    state = make_state()
    occurrence_id = state.abbreviation_candidates[0].occurrence_id
    with pytest.raises(IllegalCleanupAction):
        state.decide(occurrence_id, "accept")


def test_is_phase_settled_true_only_once_every_candidate_decided() -> None:
    state = make_state()
    ids = [c.occurrence_id for c in state.abbreviation_candidates]
    assert state.is_phase_settled("abbreviation") is False
    state.decide(ids[0], "apply_once")
    assert state.is_phase_settled("abbreviation") is False
    state.decide(ids[1], "skip")
    assert state.is_phase_settled("abbreviation") is True


def test_zero_candidate_phase_is_vacuously_settled() -> None:
    state = WorkingState(
        content_hash="hash2",
        source_kind="text_file",
        abbreviation_base_passages=(Passage(index=0, text="nothing here"),),
        abbreviation_candidates=(),
    )
    assert state.is_phase_settled("abbreviation") is True
    assert state.current_view() is None
    assert state.has_any_cleanup_work() is False


def test_install_spelling_freezes_base_and_switches_phase() -> None:
    state = make_state()
    for candidate in state.abbreviation_candidates:
        state.decide(candidate.occurrence_id, "apply_once")
    settled_text = state.working_passages("abbreviation")[0].text
    state.install_spelling([Passage(index=0, text=settled_text)], [])
    assert state.phase == "spelling"
    assert state.spelling_installed() is True
    assert state.spelling_base_passages == (Passage(index=0, text=settled_text),)
    assert state.is_fully_resolved() is True  # zero spelling candidates too


def test_is_fully_resolved_requires_spelling_installed() -> None:
    state = make_state()
    for candidate in state.abbreviation_candidates:
        state.decide(candidate.occurrence_id, "apply_once")
    assert state.is_phase_settled("abbreviation") is True
    assert state.is_fully_resolved() is False  # spelling not installed yet


def test_re_decision_recomputes_working_text() -> None:
    state = make_state()
    occurrence_id = state.abbreviation_candidates[0].occurrence_id
    state.decide(occurrence_id, "apply_once")
    assert state.working_passages()[0].text.startswith("with")
    state.decide(occurrence_id, "skip")
    assert state.working_passages()[0].text.startswith("w/")
    assert state.working_draft_revision == 2


def test_identical_re_decision_does_not_advance_working_revision() -> None:
    state = make_state()
    occurrence_id = state.abbreviation_candidates[0].occurrence_id
    state.decide(occurrence_id, "apply_once")
    state.decide(occurrence_id, "apply_once")
    assert state.interaction_revision == 2
    assert state.working_draft_revision == 1


def test_current_view_context_and_sentences() -> None:
    text = "First sentence here. The w/ occurrence sentence. Last sentence follows."
    passages = [Passage(index=0, text=text)]
    candidates = find_candidates(passages, [MappingRow("m1", "w/", "with", True)])
    state = WorkingState(
        content_hash="hash3",
        source_kind="text_file",
        abbreviation_base_passages=tuple(passages),
        abbreviation_candidates=tuple(candidates),
    )
    view = state.current_view()
    assert view is not None
    assert view.sentence == "The w/ occurrence sentence."
    assert view.before_sentence == "First sentence here."
    assert view.after_sentence == "Last sentence follows."
    assert "occurrence sentence" in view.context_after or "The" in view.context_before
