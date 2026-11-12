from __future__ import annotations

import math


def score_binary(
    probability: float, outcome: bool | int, base_rate: float | None = None
) -> dict[str, float | None]:
    """Score a binary forecast with lower-is-better Brier and log scores."""
    observed = int(bool(outcome))
    brier = (probability - observed) ** 2
    clipped = min(0.99, max(0.01, probability))
    assigned = clipped if observed else 1 - clipped
    log_score = -math.log(assigned)

    skill = None
    if base_rate is not None:
        reference_brier = (base_rate - observed) ** 2
        if reference_brier > 0:
            skill = 1 - (brier / reference_brier)

    return {
        "brier": brier,
        "log_score": log_score,
        "skill_vs_base_rate": skill,
    }

