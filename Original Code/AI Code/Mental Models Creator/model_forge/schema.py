from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import re
from typing import Any, Literal
from uuid import uuid4

Sign = Literal["positive", "negative", "mixed", "unknown"]


def namespace_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


@dataclass(slots=True)
class Entity:
    name: str
    kind: str = "concept"
    namespace: str = ""
    aliases: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Entity name cannot be empty")
        self.namespace = self.namespace or namespace_key(self.name)


@dataclass(slots=True)
class Edge:
    cause: str
    effect: str
    sign: Sign = "unknown"
    magnitude: str = "unknown"
    lag: str = "unknown"
    claim: str = ""
    support: Literal["stated", "inferred", "unsupported"] = "inferred"
    source_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    hardening: list[dict[str, Any]] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if self.sign not in {"positive", "negative", "mixed", "unknown"}:
            raise ValueError(f"Invalid edge sign: {self.sign}")
        if not self.cause.strip() or not self.effect.strip():
            raise ValueError("Edges require cause and effect")
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


@dataclass(slots=True)
class Prediction:
    statement: str
    due_date: str
    confidence: float
    edge_ids: list[str] = field(default_factory=list)
    observable: str = ""
    status: Literal["open", "correct", "incorrect", "ambiguous"] = "open"
    outcome: float | None = None
    resolved_at: str | None = None
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("Prediction statement cannot be empty")
        try:
            date.fromisoformat(self.due_date)
        except ValueError as exc:
            raise ValueError("Prediction due_date must be YYYY-MM-DD") from exc
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


@dataclass(slots=True)
class Source:
    id: str
    kind: str
    locator: str
    title: str = ""
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class CausalModel:
    name: str
    scope: str
    boundary_conditions: list[str] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    predictions: list[Prediction] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    provenance: dict[str, Source] = field(default_factory=dict)
    compressions: dict[str, str] = field(default_factory=dict)
    transfer_tests: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    calibration: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    revision: int = 1
    schema_version: str = "model-forge/v1"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def validate(self, require_predictions: bool = False) -> None:
        if not self.name.strip() or not self.scope.strip():
            raise ValueError("Model requires name and scope")
        keys = {entity.namespace for entity in self.entities}
        if len(keys) != len(self.entities):
            raise ValueError("Entity namespace keys must be unique within a model")
        if require_predictions and not self.predictions:
            raise ValueError("Model rejected: prediction extraction produced zero predictions")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CausalModel":
        values = dict(data)
        values["entities"] = [Entity(**item) for item in values.get("entities", [])]
        values["edges"] = [Edge(**item) for item in values.get("edges", [])]
        values["predictions"] = [Prediction(**item) for item in values.get("predictions", [])]
        values["provenance"] = {
            key: Source(**value) for key, value in values.get("provenance", {}).items()
        }
        return cls(**values)
