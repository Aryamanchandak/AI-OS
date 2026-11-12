import math

import pytest

from decision_tracker.scoring import score_binary


def test_binary_scores_winning_forecast() -> None:
    result = score_binary(0.7, True, base_rate=0.5)

    assert result["brier"] == pytest.approx(0.09)
    assert result["log_score"] == pytest.approx(-math.log(0.7))
    assert result["skill_vs_base_rate"] == pytest.approx(0.64)


def test_log_score_clips_certainty() -> None:
    result = score_binary(1.0, False)

    assert result["brier"] == 1.0
    assert result["log_score"] == pytest.approx(-math.log(0.01))
    assert result["skill_vs_base_rate"] is None

