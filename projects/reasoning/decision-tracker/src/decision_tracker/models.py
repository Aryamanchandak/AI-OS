from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DecisionClass(StrEnum):
    FORECAST = "FORECAST"
    ALLOCATION = "ALLOCATION"
    ANALYTIC = "ANALYTIC"
    BUILD = "BUILD"


class DecisionStatus(StrEnum):
    DRAFT = "DRAFT"
    COMMITTED = "COMMITTED"
    LIVE = "LIVE"
    RESOLVED = "RESOLVED"
    VOID = "VOID"
    SUPERSEDED = "SUPERSEDED"


class ClaimType(StrEnum):
    BINARY = "binary"
    CATEGORICAL = "categorical"
    NUMERIC_INTERVAL = "numeric_interval"


class SourceClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL_NON_MATERIAL = "internal_non_material"
    BLOCKED = "blocked"


class Attribution(StrEnum):
    RIGHT_FOR_RIGHT_REASONS = "RIGHT_FOR_RIGHT_REASONS"
    RIGHT_FOR_WRONG_REASONS = "RIGHT_FOR_WRONG_REASONS"
    WRONG_BUT_SOUND = "WRONG_BUT_SOUND"
    WRONG_AND_UNSOUND = "WRONG_AND_UNSOUND"


class Reversibility(StrEnum):
    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"


class BaseRate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Annotated[float, Field(ge=0, le=1)]
    source: str = Field(min_length=1)


class Distribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p10: float
    p50: float
    p90: float

    @model_validator(mode="after")
    def ordered(self) -> "Distribution":
        if not self.p10 <= self.p50 <= self.p90:
            raise ValueError("distribution must satisfy p10 <= p50 <= p90")
        return self


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    resolution_source: str | None = None
    resolution_date: date | None = None
    resolution_triggers: list[str] = Field(default_factory=list)
    type: ClaimType = ClaimType.BINARY
    probability: Annotated[float | None, Field(ge=0, le=1)] = None
    distribution: Distribution | None = None
    success_metric: str | None = None

    @model_validator(mode="after")
    def matches_claim_type(self) -> "Claim":
        if self.type == ClaimType.BINARY and self.distribution is not None:
            raise ValueError("binary claims cannot define a numeric distribution")
        if self.type == ClaimType.NUMERIC_INTERVAL and self.probability is not None:
            raise ValueError("numeric interval claims cannot define a binary probability")
        return self


class Alternative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option: str = Field(min_length=1)
    why_rejected: str = Field(min_length=1)


class Reasoning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_rate: BaseRate | None = None
    drivers: list[str] = Field(default_factory=list)
    key_assumption: str | None = None
    falsifiers: list[str] = Field(default_factory=list)
    alternatives_considered: list[Alternative] = Field(default_factory=list)
    premortem: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")

    taken: bool = False
    description: str | None = None
    size_bps_risk: float | None = None
    counterfactual: str | None = None
    reversibility: Reversibility | None = None
    cost_of_delay: str | None = None


class Process(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_rate_stated: bool = False
    alternatives_count: int = 0
    falsifier_named: bool = False
    premortem_done: bool = False
    outside_view_sought: bool = False
    resolution_machine_checkable: bool = False
    process_score: Annotated[float, Field(ge=0, le=1)] = 0


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_at: datetime
    outcome: bool | float | str
    evidence: str = Field(min_length=1)
    resolver_source: str | None = None
    brier: float | None = None
    log_score: float | None = None
    skill_vs_base_rate: float | None = None
    attribution: Attribution | None = None
    failure_tags: list[str] = Field(default_factory=list)
    lesson: str | None = None
    interval_hit: bool | None = None
    counterfactual_outcome: float | None = None
    direction_score: float | None = None
    sizing_score: float | None = None
    timing_score: float | None = None


class Integrity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit_hash: str | None = None
    prev_hash: str | None = None
    amendments: list[dict[str, Any]] = Field(default_factory=list)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime
    created_via: str = "cli"
    author: str
    decision_class: DecisionClass = Field(alias="class")
    status: DecisionStatus = DecisionStatus.DRAFT
    source_classification: SourceClassification
    title: str = Field(min_length=1)
    domain: list[str] = Field(default_factory=list)
    horizon_days: int | None = None
    claim: Claim
    reasoning: Reasoning = Field(default_factory=Reasoning)
    action: Action | None = None
    process: Process = Field(default_factory=Process)
    resolution: Resolution | None = None
    integrity: Integrity = Field(default_factory=Integrity)
    backfilled: bool = False
    supersedes_id: str | None = None
    red_team: str | None = None
    contradicts_ids: list[str] = Field(default_factory=list)


class DecisionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_via: str = "cli"
    author: str
    decision_class: DecisionClass = Field(alias="class")
    source_classification: SourceClassification
    title: str = Field(min_length=1)
    domain: list[str] = Field(default_factory=list)
    claim: Claim
    reasoning: Reasoning = Field(default_factory=Reasoning)
    action: Action | None = None
    backfilled: bool = False
    supersedes_id: str | None = None
    red_team: str | None = None
    contradicts_ids: list[str] = Field(default_factory=list)


class ResolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: bool | float | str
    evidence: str = Field(min_length=1)
    resolver_source: str | None = None
    attribution: Attribution | None = None
    failure_tags: list[str] = Field(default_factory=list)
    lesson: str | None = None
    automated: bool = False
    counterfactual_outcome: float | None = None
    direction_score: float | None = None
    sizing_score: float | None = None
    timing_score: float | None = None

    @model_validator(mode="after")
    def controlled_tags(self) -> "ResolutionInput":
        allowed={"ANCHORING","BASE_RATE_NEGLECT","OVERPRECISION","CONFIRMATION","CONSENSUS_DRIFT","RECENCY","WRONG_REFERENCE_CLASS","MODEL_RIGHT_TIMING_WRONG","SIZED_WRONG","IGNORED_REDTEAM","ASSUMPTION_INVALIDATED_NO_ACTION","EXOGENOUS"}
        unknown=set(self.failure_tags)-allowed
        if unknown:raise ValueError(f"unknown failure tags: {sorted(unknown)}")
        return self


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    decision_id: str
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]
    prev_event_hash: str | None
    event_hash: str
