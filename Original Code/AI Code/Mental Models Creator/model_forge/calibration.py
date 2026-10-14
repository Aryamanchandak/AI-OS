from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt

from .schema import CausalModel, Prediction


def resolve_prediction(model: CausalModel, prediction_id: str, outcome: float, note: str = "") -> Prediction:
    if outcome < 0 or outcome > 1:
        raise ValueError("Outcome must be between 0 (false) and 1 (true)")
    try:
        prediction = next(item for item in model.predictions if item.id == prediction_id)
    except StopIteration as exc:
        raise KeyError(f"No prediction found for {prediction_id!r}") from exc
    prediction.outcome = float(outcome)
    prediction.status = "correct" if outcome >= 0.75 else "incorrect" if outcome <= 0.25 else "ambiguous"
    prediction.observable = f"{prediction.observable} Outcome note: {note}".strip()
    prediction.resolved_at = datetime.now(timezone.utc).isoformat()
    update_calibration(model)
    return prediction


def update_calibration(model: CausalModel) -> dict:
    resolved = [item for item in model.predictions if item.outcome is not None]
    if not resolved:
        model.confidence = 0.0
        model.calibration = {"resolved": 0, "brier_score": None, "earned_confidence": 0.0}
        return model.calibration
    brier = sum((item.confidence - float(item.outcome)) ** 2 for item in resolved) / len(resolved)
    accuracy = sum(1 - abs(round(item.confidence) - float(item.outcome)) for item in resolved) / len(resolved)
    calibration_quality = max(0.0, 1.0 - sqrt(brier))
    evidence_weight = min(1.0, len(resolved) / 10)
    earned = (0.65 * calibration_quality + 0.35 * accuracy) * evidence_weight
    model.confidence = round(earned, 4)
    model.calibration = {
        "resolved": len(resolved), "brier_score": round(brier, 4),
        "accuracy": round(accuracy, 4), "evidence_weight": evidence_weight,
        "earned_confidence": model.confidence,
    }
    return model.calibration

