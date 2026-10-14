from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def stable_id(prefix: str, payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{sha256(encoded.encode()).hexdigest()[:16]}"


class ComponentType(StrEnum):
    EMPIRICAL = "empirical"
    NORMATIVE = "normative"
    DEFINITIONAL = "definitional"


class PremiseType(StrEnum):
    EMPIRICAL = "empirical"
    CAUSAL = "causal-mechanism"
    DEFINITIONAL = "definitional"
    NORMATIVE = "normative"


class VerificationGrade(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    CONTESTED = "contested"
    UNSUPPORTED = "unsupported"
    FABRICATED = "fabricated"
    NOT_APPLICABLE = "not-applicable"


class SourceTier(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class SourceStance(StrEnum):
    SUPPORTS = "supports"
    CONTESTS = "contests"
    NEUTRAL = "neutral"


class ClaimComponent(BaseModel):
    text: str = Field(min_length=1)
    type: ComponentType


class ClaimCard(BaseModel):
    canonical_claim: str = Field(min_length=1)
    components: list[ClaimComponent] = Field(min_length=1)
    scope: str = "unspecified"
    time_horizon: str = "unspecified"
    falsifiable: bool
    falsifiability_note: str
    claim_hash: str


class Source(BaseModel):
    id: str = Field(default_factory=lambda: f"src_{uuid4().hex[:12]}")
    title: str = Field(min_length=1)
    publisher: str = ""
    author_or_advocate: str = ""
    url: str = ""
    excerpt: str = Field(min_length=1)
    published_at: str = ""
    tier: SourceTier = SourceTier.SECONDARY
    stance: SourceStance = SourceStance.SUPPORTS
    supports_node_ids: list[str] = Field(default_factory=list)


class PremiseNode(BaseModel):
    id: str
    text: str = Field(min_length=1)
    type: PremiseType
    load_bearing: bool = False
    strength: str = "proposed"
    cited_source_ids: list[str] = Field(default_factory=list)


class PremiseEdge(BaseModel):
    source_id: str
    target_id: str
    relation: str = "supports"


class VerificationResult(BaseModel):
    node_id: str
    grade: VerificationGrade
    source_ids: list[str] = Field(default_factory=list)
    note: str


class ArgumentGraph(BaseModel):
    claim_hash: str
    nodes: list[PremiseNode]
    edges: list[PremiseEdge]
    verifications: list[VerificationResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> "ArgumentGraph":
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Premise node IDs must be unique")
        known = set(ids)
        for edge in self.edges:
            if edge.source_id not in known or edge.target_id not in known:
                raise ValueError("Every edge endpoint must reference an existing node")
        return self


class ProponentStatus(StrEnum):
    SOURCED = "SOURCED"
    CONSTRUCTED = "CONSTRUCTED — no real proponent located"


class AnalysisRun(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(default_factory=lambda: f"run_{uuid4().hex}")
    created_at: datetime = Field(default_factory=utc_now)
    provider: str
    claim_card: ClaimCard
    graph: ArgumentGraph
    sources: list[Source] = Field(default_factory=list)
    proponent_status: ProponentStatus
    proponent_names: list[str] = Field(default_factory=list)
    rendered_steelman: str


class ForensicFlagDefinition(BaseModel):
    code: str
    name: str
    prompt: str


class ForensicAssessment(BaseModel):
    id: str = Field(default_factory=lambda: f"fa_{uuid4().hex}")
    created_at: datetime = Field(default_factory=utc_now)
    company: str
    flag_code: str
    observation: str
    benign_explanation: str
    management_evidence: str = ""
    contradictory_evidence: str = ""
    residual_risk: str
    verification_grade: VerificationGrade
    escalate_requested: bool = False
    escalation_allowed: bool = False
    gate_reasons: list[str] = Field(default_factory=list)


class FrameMode(StrEnum):
    MECHANISM = "mechanism/causal"
    BASE_RATE = "base rate + historical analog"
    POLITICAL_ECONOMY = "political economy / incentives"
    ASYMMETRIC_PAYOFF = "asymmetric payoff / option value"
    CASCADE = "second-order cascade"
    TAIL = "tail-justification"


class Side(StrEnum):
    CLAIM = "claim"
    NEGATION = "negation"


class BudgetUsage(BaseModel):
    side: Side
    token_budget: int
    search_budget: int
    tokens_used: int
    searches_used: int


class HardeningRound(BaseModel):
    round_number: int
    attack: str
    repair: str
    survived: bool
    retreat_position: str = ""


class Prediction(BaseModel):
    id: str
    side: Side
    proposition: str
    metric: str
    direction: str
    threshold: float
    unit: str
    deadline: str


class Crux(BaseModel):
    id: str
    disputed_proposition: str
    claim_prediction: str
    negation_prediction: str
    settling_observation: str


class RubricResult(BaseModel):
    score: int
    threshold: int
    passed: bool
    checks: dict[str, bool]
    regeneration_count: int = 0


class SideAnalysis(BaseModel):
    side: Side
    run: AnalysisRun
    frames: dict[FrameMode, str]
    hardening: list[HardeningRound]
    retreat_path: list[str]
    predictions: list[Prediction]
    budget: BudgetUsage


class DualAnalysis(BaseModel):
    id: str = Field(default_factory=lambda: f"dual_{uuid4().hex}")
    created_at: datetime = Field(default_factory=utc_now)
    claim: SideAnalysis
    negation: SideAnalysis
    blinded_order: list[Side]
    cruxes: list[Crux]
    rubric: RubricResult
    dag_log: list[str]


class TrackerEntry(BaseModel):
    prediction: Prediction
    registered_at: datetime = Field(default_factory=utc_now)
    resolved: bool = False
    observed_value: float | None = None
    outcome: bool | None = None
    confidence: float = Field(default=0.65, ge=0, le=1)


class CalibrationSummary(BaseModel):
    resolved_count: int
    brier_score: float | None
    accuracy: float | None
