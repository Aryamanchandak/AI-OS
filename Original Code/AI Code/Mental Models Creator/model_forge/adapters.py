from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any, Protocol
from urllib import error, request
from uuid import uuid4

from .calibration import resolve_prediction
from .schema import CausalModel, Edge

ADAPTER_SCHEMA = "model-forge.adapter/v1"


@dataclass(slots=True)
class Envelope:
    operation: str
    payload: dict[str, Any]
    schema: str = ADAPTER_SCHEMA
    request_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        self.request_id = self.request_id or str(uuid4())
        self.created_at = self.created_at or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SteelmanAdapter(Protocol):
    def harden(self, model: CausalModel, edge_id: str) -> dict[str, Any]: ...


class MirfishAdapter(Protocol):
    def run_forward(self, model: CausalModel, observations: str) -> dict[str, Any]: ...


class DecisionTrackerAdapter(Protocol):
    def score(self, model: CausalModel, prediction_id: str, outcome: float, note: str = "") -> dict[str, Any]: ...


class LocalSteelman:
    def harden(self, model: CausalModel, edge_id: str) -> dict[str, Any]:
        edge = _edge(model, edge_id)
        missing = [] if edge.source_ids else ["No source directly supports this edge"]
        assessment = {
            "hardened_at": datetime.now(timezone.utc).isoformat(),
            "strongest_case": f"The relationship is credible when the mechanism in '{edge.claim or edge.cause + ' → ' + edge.effect}' operates and boundary conditions hold.",
            "alternative_explanations": [f"A third variable may drive both {edge.cause} and {edge.effect}", f"The observed direction may reverse outside the stated scope"],
            "missing_evidence": missing,
            "falsifier": f"Observe {edge.cause} change without the predicted directional response in {edge.effect}.",
            "verdict": "hypothesis" if missing or edge.support == "unsupported" else "provisionally hardened",
        }
        edge.hardening.append(assessment)
        if not missing and edge.support == "stated":
            edge.confidence = min(0.95, edge.confidence + 0.05)
        return Envelope("steelman.harden-edge", {
            "model_id": model.id, "edge": asdict(edge),
            **assessment,
        }).to_dict()


class LocalMirfish:
    def run_forward(self, model: CausalModel, observations: str) -> dict[str, Any]:
        terms = {_term(word) for word in observations.casefold().split() if len(_term(word)) > 3}
        assessments = []
        for prediction in model.predictions:
            prediction_terms = {_term(word) for word in (prediction.statement + " " + prediction.observable).casefold().split() if len(_term(word)) > 3}
            overlap = sorted(terms & prediction_terms)
            relevance = min(1.0, len(overlap) / max(2, min(8, len(prediction_terms))))
            evaluation = {
                "evaluated_at": datetime.now(timezone.utc).isoformat(), "relevance": round(relevance, 3),
                "matched_terms": overlap, "evidence": observations[:1000],
                "assessment": "possible signal" if relevance >= .25 else "insufficient matching evidence",
            }
            prediction.evaluations.append(evaluation)
            assessments.append({"prediction_id": prediction.id, **evaluation})
        return Envelope("mirfish.run-forward", {
            "model_id": model.id, "observation": observations,
            "triggered_prediction_ids": [a["prediction_id"] for a in assessments if a["relevance"] >= .25],
            "assessments": assessments,
        }).to_dict()


class LocalDecisionTracker:
    def score(self, model: CausalModel, prediction_id: str, outcome: float, note: str = "") -> dict[str, Any]:
        prediction = resolve_prediction(model, prediction_id, outcome, note)
        return Envelope("decision-tracker.score", {
            "model_id": model.id, "prediction_id": prediction.id,
            "status": prediction.status, "calibration": model.calibration,
        }).to_dict()


class HTTPJSONAdapter:
    """Concrete transport for independently deployed AI OS services."""
    def __init__(self, endpoint: str, token: str = "") -> None:
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("Adapter endpoint must use http or https")
        self.endpoint, self.token = endpoint, token

    def send(self, envelope: Envelope) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        req = request.Request(self.endpoint, json.dumps(envelope.to_dict()).encode(), headers, method="POST")
        try:
            with request.urlopen(req, timeout=60) as response: result = json.load(response)
        except error.HTTPError as exc:
            raise RuntimeError(f"Adapter request failed ({exc.code}): {exc.read().decode(errors='replace')[:400]}") from exc
        if result.get("schema") != ADAPTER_SCHEMA:
            raise RuntimeError("Adapter returned an incompatible schema")
        return result


class RemoteSteelman(HTTPJSONAdapter):
    def harden(self, model: CausalModel, edge_id: str) -> dict[str, Any]:
        return self.send(Envelope("steelman.harden-edge", {"model": model.to_dict(), "edge_id": edge_id}))


class RemoteMirfish(HTTPJSONAdapter):
    def run_forward(self, model: CausalModel, observations: str) -> dict[str, Any]:
        return self.send(Envelope("mirfish.run-forward", {"model": model.to_dict(), "observations": observations}))


class RemoteDecisionTracker(HTTPJSONAdapter):
    def score(self, model: CausalModel, prediction_id: str, outcome: float, note: str = "") -> dict[str, Any]:
        return self.send(Envelope("decision-tracker.score", {"model": model.to_dict(), "prediction_id": prediction_id, "outcome": outcome, "note": note}))


def _edge(model: CausalModel, identifier: str) -> Edge:
    try:
        return next(item for item in model.edges if item.id == identifier)
    except StopIteration as exc:
        raise KeyError(f"No edge found for {identifier!r}") from exc


def _term(value: str) -> str:
    return "".join(character for character in value if character.isalnum())
