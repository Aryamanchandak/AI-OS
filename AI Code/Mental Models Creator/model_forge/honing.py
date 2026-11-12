from __future__ import annotations

from dataclasses import dataclass
import json

from .ai import ForgeEngine, LocalEngine, local_predictions
from .schema import CausalModel, Prediction


@dataclass(slots=True)
class HoningResult:
    model: CausalModel
    rejected: bool
    reasons: list[str]


class Honer:
    def __init__(self, engine: ForgeEngine) -> None:
        self.engine = engine

    def run(self, model: CausalModel, prediction_count: int = 3, adjacent_domain: str = "") -> HoningResult:
        self.compress(model)
        if not model.compressions.get("15") or not model.compressions.get("40"):
            return HoningResult(model, True, ["Compression failed: causal structure did not survive both limits"])
        self.extract_predictions(model, prediction_count)
        self.hunt_anomalies(model)
        self.transfer_test(model, adjacent_domain)
        reasons = [] if len(model.predictions) == prediction_count else [f"Prediction extraction produced {len(model.predictions)} of {prediction_count} required predictions"]
        return HoningResult(model, bool(reasons), reasons)

    def compress(self, model: CausalModel) -> None:
        if isinstance(self.engine, LocalEngine):
            basis = self._basis(model)
            model.compressions["40"] = self._words(basis, 40)
            model.compressions["15"] = self._words(basis, 15)
            return
        data = self.engine.complete_json(
            "Compress the causal structure at 40 words and at 15 words. Preserve mechanism, direction, and boundary. Return keys '40' and '15'.",
            model.to_dict(),
        )
        model.compressions = {"40": str(data.get("40", "")), "15": str(data.get("15", ""))}

    def extract_predictions(self, model: CausalModel, count: int) -> None:
        count = max(1, min(20, int(count)))
        if isinstance(self.engine, LocalEngine):
            model.predictions = local_predictions(model, count)
            return
        data = self.engine.complete_json(
            f"Emit exactly {count} falsifiable predictions grounded in model edges. Every prediction must have a future YYYY-MM-DD due_date, 0-1 confidence, observable, and edge_ids. Return {{'predictions': [...]}}.",
            model.to_dict(),
        )
        model.predictions = [Prediction(**item) for item in data.get("predictions", [])]

    def hunt_anomalies(self, model: CausalModel) -> None:
        if isinstance(self.engine, LocalEngine):
            names = {entity.namespace: entity.name for entity in model.entities}
            model.anomalies = [
                f"Counterexample: {names.get(edge.cause, edge.cause)} changes but {names.get(edge.effect, edge.effect)} does not; edge {edge.id} breaks first."
                for edge in model.edges
            ] or ["No causal edge exists to challenge; the model cannot yet explain observations."]
            return
        data = self.engine.complete_json(
            "Actively seek concrete counterexamples. For each, identify which edge breaks first and what must be true for the model to be wrong. Return {'anomalies': [strings]}.",
            model.to_dict(),
        )
        model.anomalies = [str(item) for item in data.get("anomalies", [])]

    def transfer_test(self, model: CausalModel, adjacent_domain: str) -> None:
        target = adjacent_domain or "an adjacent organizational or market setting"
        if isinstance(self.engine, LocalEngine):
            transferable = bool(model.edges and all(edge.sign != "unknown" for edge in model.edges))
            model.transfer_tests.append({
                "domain": target,
                "generalizes": transferable,
                "analysis": "Directional causal structure can be tested in the target domain." if transferable else "Unknown edge direction prevents a defensible transfer.",
            })
            return
        data = self.engine.complete_json(
            f"Apply this model to {target}. Decide whether structure generalizes and explain the mapping and failure points. Return domain, generalizes boolean, analysis.",
            model.to_dict(),
        )
        model.transfer_tests.append(data)

    @staticmethod
    def _basis(model: CausalModel) -> str:
        names = {entity.namespace: entity.name for entity in model.entities}
        claims = [f"{names.get(e.cause, e.cause)} {e.sign}ly affects {names.get(e.effect, e.effect)}" for e in model.edges]
        return f"Within {model.scope}, " + "; ".join(claims) + ". " + " ".join(model.boundary_conditions)

    @staticmethod
    def _words(text: str, limit: int) -> str:
        words = text.split()
        return " ".join(words[:limit]).rstrip(".,;") + ("…" if len(words) > limit else "")
