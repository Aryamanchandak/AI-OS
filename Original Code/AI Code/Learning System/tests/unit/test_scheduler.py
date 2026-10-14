"""Unit tests for the FSRS scheduler."""

import pytest
from datetime import datetime

from study_system.scheduler import FSRSScheduler, DEFAULT_WEIGHTS, _forgetting_curve
from study_system.types.card import CardRating, FSRSState


@pytest.fixture
def scheduler():
    return FSRSScheduler(fuzz_range=(1.0, 1.0))  # no fuzz for deterministic tests


class TestForgettingCurve:
    def test_zero_elapsed_is_one(self):
        r = _forgetting_curve(0, 10.0)
        assert abs(r - 1.0) < 0.01

    def test_at_stability_is_ninety_percent(self):
        s = 10.0
        r = _forgetting_curve(s, s)
        assert abs(r - 0.9) < 0.01

    def test_zero_stability(self):
        r = _forgetting_curve(5, 0)
        assert r == 0.0


class TestFirstReview:
    def test_again_goes_to_relearning(self, scheduler):
        state = FSRSState()
        new_state = scheduler.rate(state, CardRating.again)
        assert new_state.state == "relearning"
        assert new_state.reps == 1
        assert new_state.scheduled_days == 1

    def test_good_goes_to_learning(self, scheduler):
        state = FSRSState()
        new_state = scheduler.rate(state, CardRating.good)
        assert new_state.state == "learning"
        assert new_state.reps == 1

    def test_easy_goes_to_review(self, scheduler):
        state = FSRSState()
        new_state = scheduler.rate(state, CardRating.easy)
        assert new_state.state == "review"
        assert new_state.reps == 1

    def test_stability_positive_after_first_review(self, scheduler):
        state = FSRSState()
        for rating in [1, 2, 3, 4]:
            new_state = scheduler.rate(FSRSState(), rating)
            assert new_state.stability > 0

    def test_difficulty_in_range(self, scheduler):
        for rating in [1, 2, 3, 4]:
            new_state = scheduler.rate(FSRSState(), rating)
            assert 1.0 <= new_state.difficulty <= 10.0


class TestSubsequentReviews:
    def test_lapses_increase_on_again(self, scheduler):
        state = FSRSState(stability=5.0, difficulty=5.0, reps=3, state="review")
        new_state = scheduler.rate(state, CardRating.again)
        assert new_state.lapses == 1

    def test_no_lapse_on_good(self, scheduler):
        state = FSRSState(stability=5.0, difficulty=5.0, reps=3, state="review")
        new_state = scheduler.rate(state, CardRating.good)
        assert new_state.lapses == 0

    def test_next_due_set(self, scheduler):
        state = FSRSState(stability=5.0, difficulty=5.0, reps=1, state="review")
        new_state = scheduler.rate(state, CardRating.good)
        assert new_state.next_due_at is not None
        assert new_state.next_due_at > datetime.utcnow()


class TestFuzz:
    def test_fuzz_produces_range(self):
        sched = FSRSScheduler(fuzz_range=(0.8, 1.2))
        results = {sched._fuzz(10.0) for _ in range(50)}
        assert len(results) > 1  # not all identical
        assert all(8.0 <= r <= 12.0 for r in results)

    def test_no_fuzz_is_deterministic(self):
        sched = FSRSScheduler(fuzz_range=(1.0, 1.0))
        results = {sched._fuzz(10.0) for _ in range(10)}
        assert results == {10.0}
