"""FSRS-4.5 scheduler with fuzz.

Implements the Free Spaced Repetition Scheduler algorithm (FSRS v4.5).
Reference weights from the py-fsrs project (MIT licence).
Stdlib only — no external dependencies.

Key concepts:
    S = stability (expected days to 90% retention)
    D = difficulty (1-10 scale)
    R = retrievability at time t: R(t) = 0.9^(t/S)
"""

import math
import random
from datetime import datetime, timedelta
from typing import Optional

from study_system.types.card import CardRating, FSRSState

# FSRS-4.5 default weights (19 parameters, from py-fsrs reference)
DEFAULT_WEIGHTS: list[float] = [
    0.4072, 1.1829, 3.1262, 15.4722,
    7.2102, 0.5316, 1.0651, 0.0589,
    1.5330, 0.1544, 1.0071, 1.9395,
    0.1100, 0.2900, 2.2700, 0.2500,
    2.9898, 0.5100, 0.4300,
]

DECAY = -0.5
FACTOR = 19 / 81  # = 0.2345...


def _forgetting_curve(elapsed_days: float, stability: float) -> float:
    """Retrievability: probability of recall after elapsed_days given stability."""
    if stability <= 0:
        return 0.0
    return float((1 + FACTOR * elapsed_days / stability) ** DECAY)


def _initial_stability(rating: int, w: list[float]) -> float:
    """Stability after first review based on rating (1-4)."""
    return w[rating - 1]  # w[0]..w[3] for again/hard/good/easy


def _initial_difficulty(rating: int, w: list[float]) -> float:
    d = w[4] - math.exp(w[5] * (rating - 1)) + 1
    return max(1.0, min(10.0, d))


def _next_difficulty(d: float, rating: int, w: list[float]) -> float:
    delta_d = -w[6] * (rating - 3)
    new_d = d + delta_d * (10 - d) / 9
    # Mean-reversion toward initial difficulty with rating=2
    revert_target = _initial_difficulty(2, w)
    new_d = new_d + w[7] * (revert_target - new_d)
    return max(1.0, min(10.0, new_d))


def _next_stability_recall(s: float, d: float, r: float, rating: int, w: list[float]) -> float:
    """Stability update when card is recalled (rating >= 2)."""
    hard_penalty = w[15] if rating == CardRating.hard else 1.0
    easy_bonus = w[16] if rating == CardRating.easy else 1.0
    return float(s * (
        math.exp(w[8])
        * (11 - d)
        * (s ** -w[9])
        * (math.exp(w[10] * (1 - r)) - 1)
        * hard_penalty
        * easy_bonus
        + 1
    ))


def _next_stability_forget(s: float, d: float, r: float, w: list[float]) -> float:
    """Stability update when card is forgotten (rating == 1)."""
    return float(
        w[11]
        * (d ** -w[12])
        * ((s + 1) ** w[13] - 1)
        * math.exp(w[14] * (1 - r))
    )


class FSRSScheduler:
    """FSRS-4.5 scheduler.

    Instantiate once with weights (default = FSRS defaults). Pass to reviewer.
    """

    def __init__(
        self,
        weights: Optional[list[float]] = None,
        fuzz_range: tuple[float, float] = (0.95, 1.05),
    ) -> None:
        self._w = weights or DEFAULT_WEIGHTS
        self._fuzz_range = fuzz_range

    def rate(self, state: FSRSState, rating: int, now: Optional[datetime] = None) -> FSRSState:
        """Apply a review rating and return the new FSRSState."""
        if now is None:
            now = datetime.utcnow()

        r_val = CardRating(rating)
        w = self._w

        elapsed = state.elapsed_days

        if state.state == "new" or state.reps == 0:
            # First review
            new_stability = _initial_stability(rating, w)
            new_difficulty = _initial_difficulty(rating, w)
            if r_val == CardRating.again:
                new_state = "relearning"
                interval = 1
            elif r_val == CardRating.hard:
                new_state = "learning"
                interval = 1
            elif r_val == CardRating.good:
                new_state = "learning"
                interval = max(1, round(new_stability))
            else:  # easy
                new_state = "review"
                interval = max(1, round(new_stability))
        else:
            retrievability = _forgetting_curve(elapsed, state.stability)
            new_difficulty = _next_difficulty(state.difficulty, rating, w)

            if r_val == CardRating.again:
                new_stability = _next_stability_forget(state.stability, new_difficulty, retrievability, w)
                new_state = "relearning"
                interval = 1
            else:
                new_stability = _next_stability_recall(state.stability, new_difficulty, retrievability, rating, w)
                new_state = "review"
                raw_interval = new_stability * math.log(0.9) / math.log(0.9)
                interval = max(1, round(self._fuzz(new_stability)))

        lapses = state.lapses + (1 if r_val == CardRating.again and state.reps > 0 else 0)
        next_due = now + timedelta(days=interval)

        return FSRSState(
            stability=max(0.1, new_stability),
            difficulty=new_difficulty,
            elapsed_days=elapsed,
            scheduled_days=interval,
            reps=state.reps + 1,
            lapses=lapses,
            state=new_state,
            next_due_at=next_due,
        )

    def _fuzz(self, stability: float) -> float:
        """Apply a small random fuzz to prevent cards from bunching on the same day."""
        lo, hi = self._fuzz_range
        return stability * random.uniform(lo, hi)

    def schedule_with_fuzz(self, raw_interval_days: float) -> float:
        return self._fuzz(raw_interval_days)

    def maybe_retrain(
        self,
        review_history: list[dict[str, float | int]],
        min_reviews: int = 1000,
    ) -> Optional[list[float]]:
        """Retrain weights from review history. Returns new weights or None if insufficient data.

        Not wired to automatic triggering until Phase 3.
        review_history: list of {rating, elapsed_days, stability_before, stability_after}
        """
        if len(review_history) < min_reviews:
            return None
        # Placeholder: actual gradient-based FSRS optimisation would go here.
        # Returns None to indicate retraining not yet implemented.
        return None
