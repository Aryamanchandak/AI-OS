from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator, model_validator

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


# Ceilings for the lists a model fills in, so a runaway generation is cut off
# rather than silently truncating the JSON at max_output_tokens.  Set these far
# above any plausible answer: several callers (rank_candidates, generate_tasks)
# deliberately let the model overshoot and slice locally, so a tight bound would
# turn a working response into a validation failure.  The runaway that prompted
# this emitted roughly ninety candidate seeds.
MAX_GENERATED_ITEMS = {
    "candidates": 25,
    "tasks": 60,
    "claims": 250,
    "findings": 100,
    "operations": 200,
    "cases": 25,
    "ids": 250,
    "notes": 60,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FactualStatus(StrEnum):
    RUMOUR = "rumour"
    PROPOSAL = "proposal"
    ANNOUNCEMENT = "announcement"
    FORMAL_DECISION = "formal_decision"
    ENACTED = "enacted"
    IMPLEMENTED = "implemented"
    MEASURED_OUTCOME = "measured_outcome"
    ANALYSIS_OR_FORECAST = "analysis_or_forecast"
    UNCLEAR = "unclear"


class RunStatus(StrEnum):
    QUEUED = "queued"
    PRE_READING = "pre_reading"
    SELECTING = "selecting"
    BUILDING_GRAPH = "building_graph"
    RESEARCHING = "researching"
    QUANTIFYING = "quantifying"
    CHALLENGING = "challenging"
    ADJUDICATING = "adjudicating"
    COMPILING_CONTEXT = "compiling_context"
    WRITING_REPORT = "writing_report"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    REPORT_VALIDATION_FAILED = "report_validation_failed"


class NewsItem(StrictModel):
    id: str | None = None
    url: HttpUrl
    headline: str | None = None
    snippet: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    topic: str | None = None


class NewsBatch(StrictModel):
    batch_id: str | None = None
    items: list[NewsItem] = Field(min_length=1, max_length=100)
    target_market: Literal["indian_equities"] = "indian_equities"
    report_audience: str = "informed Indian equity-market reader"
    requested_at: datetime | None = None


class DiscoveryExtract(StrictModel):
    item_id: str
    canonical_url: str
    headline: str | None = None
    subheadline: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    text: str = ""
    fetched: bool = False
    failure_reason: str | None = None


class DedupGroup(StrictModel):
    id: str
    member_item_ids: list[str]
    authoritative_item_id: str
    publisher_diversity: list[str] = Field(default_factory=list)
    agreement: list[str] = Field(default_factory=list)
    disagreement: list[str] = Field(default_factory=list)
    factual_status: FactualStatus = FactualStatus.UNCLEAR


Grade = Literal["low", "medium", "high"]
SELECTION_DIMENSIONS = {
    "grounded_starting_point", "immediate_effect_plausibility", "knock_on_potential",
    "indian_equity_transmission", "researchability", "decision_relevance",
    "unresolved_assumptions",
}


class CandidateSeed(StrictModel):
    id: str
    source_item_ids: list[str]
    reported_premise: NonEmpty
    factual_status: FactualStatus
    possible_immediate_effect: NonEmpty
    possible_indian_equity_route: NonEmpty
    grades: dict[str, Grade]
    rationale: NonEmpty
    weaknesses: list[str] = Field(default_factory=list)
    selected: bool = False

    @field_validator("grades")
    @classmethod
    def all_dimensions(cls, value: dict[str, Grade]) -> dict[str, Grade]:
        if set(value) != SELECTION_DIMENSIONS:
            raise ValueError(f"grades must contain exactly {sorted(SELECTION_DIMENSIONS)}")
        return value


class CausalNode(StrictModel):
    id: str
    label: NonEmpty
    node_type: Literal["news_seed", "driver", "intermediate", "company_metric", "sector_metric", "market_outcome"]
    description: NonEmpty
    geography: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
    time_horizon: str | None = None
    status: Literal["active", "rejected", "superseded"] = "active"


class CausalEdge(StrictModel):
    id: str
    src: str
    dst: str
    mechanism: NonEmpty
    direction: Literal["positive", "negative", "mixed", "unknown"]
    strength: Literal["low", "medium", "high", "unknown"]
    confidence: Grade
    time_lag: str | None = None
    condition_text: str | None = None
    assumption_ids: list[str] = Field(default_factory=list)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    estimate_ids: list[str] = Field(default_factory=list)
    status: Literal["proposed", "supported", "mixed", "contradicted", "assumption_only", "rejected"]


class Assumption(StrictModel):
    id: str
    statement: NonEmpty
    required_for_edge_ids: list[str]
    basis: NonEmpty
    likelihood: Literal["unlikely", "possible", "likely", "unknown"]
    likelihood_basis: Literal["sourced", "inferred", "unknown"]
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    if_false_effect: NonEmpty
    material: bool


class Estimate(StrictModel):
    id: str
    metric: NonEmpty
    estimate_type: Literal["source_value", "source_range", "derived_range", "directional_only", "unknown"]
    low: Decimal | None = None
    central: Decimal | None = None
    high: Decimal | None = None
    unit: str | None = None
    period: str | None = None
    currency: str | None = None
    formula: str | None = None
    input_estimate_ids: list[str] = Field(default_factory=list)
    source_claim_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    caveat: NonEmpty

    @field_validator("high")
    @classmethod
    def ordered_range(cls, high: Decimal | None, info):
        low = info.data.get("low")
        if high is not None and low is not None and high < low:
            raise ValueError("high must be greater than or equal to low")
        return high

    @model_validator(mode="after")
    def lineage_rules(self):
        if self.estimate_type in {"source_value", "source_range"} and not self.source_claim_ids:
            raise ValueError("sourced estimates require at least one source claim")
        if self.estimate_type == "derived_range" and (not self.formula or not self.input_estimate_ids):
            raise ValueError("derived estimates require a formula and input estimates")
        return self


class SourceRecord(StrictModel):
    id: str
    url: str
    title: str
    publisher: str
    retrieved_at: datetime = Field(default_factory=utcnow)
    extracted_text: str
    content_type: str = "text/html"
    published_at: datetime | None = None
    source_type: str = "web"
    suitability_reason: str = ""
    fetch_failure: str | None = None


class EvidenceClaim(StrictModel):
    id: str
    source_id: str
    claim: NonEmpty
    exact_passage: NonEmpty
    claim_type: Literal["fact", "estimate", "forecast", "inference", "assumption"]
    stance: Literal["supports", "contradicts", "context"]
    concepts: list[str]
    geography: str | None = None
    time_horizon: str | None = None
    passage_verified: bool


class RejectedClaim(StrictModel):
    claim: str
    source_id: str
    exact_passage: str
    reason: str


class CausalGraph(StrictModel):
    version: int = Field(ge=1)
    nodes: list[CausalNode]
    edges: list[CausalEdge]
    assumptions: list[Assumption] = Field(default_factory=list)
    estimates: list[Estimate] = Field(default_factory=list)
    feedback_warnings: list[str] = Field(default_factory=list)


class GraphOperation(StrictModel):
    op: Literal["add_node", "update_node", "reject_node", "add_edge", "update_edge", "reject_edge", "add_assumption", "update_assumption", "add_estimate", "update_estimate"]
    target_id: str
    value: dict[str, Any] | None = None


class GraphPatch(StrictModel):
    operations: list[GraphOperation] = Field(max_length=MAX_GENERATED_ITEMS["operations"])
    reason: NonEmpty
    evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_GENERATED_ITEMS["ids"])
    remaining_gaps: list[str] = Field(default_factory=list, max_length=MAX_GENERATED_ITEMS["notes"])


class GraphRevision(StrictModel):
    id: str
    run_id: str
    model_call_id: str | None = None
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utcnow)
    before_version: int
    after_version: int
    operations: list[GraphOperation]
    validation_errors: list[str] = Field(default_factory=list)


class ResearchTask(StrictModel):
    id: str
    target_type: Literal["edge", "assumption", "estimate", "entity", "whole_graph"]
    target_id: str
    question: NonEmpty
    intent: Literal["confirm_premise", "test_mechanism", "find_current_conditions", "quantify", "find_indian_exposure", "find_counterevidence", "find_comparable_case"]
    preferred_source_types: list[str]
    search_queries: list[str]
    priority: Grade
    status: Literal["pending", "complete", "failed", "not_found"] = "pending"


class ChallengeFinding(StrictModel):
    id: str
    target_type: Literal["node", "edge", "assumption", "estimate"]
    target_id: str
    failure_mode: str
    explanation: str
    severity: Grade
    claim_ids: list[str] = Field(default_factory=list)


class AdjudicationDecision(StrictModel):
    finding_id: str
    decision: Literal["accept_and_revise", "accept_and_remove", "accept_and_branch", "reject_with_reason", "unresolved"]
    reason: str
    operations: list[GraphOperation] = Field(default_factory=list)


class Case(StrictModel):
    id: str
    name: str
    path_node_ids: list[str]
    path_edge_ids: list[str]
    required_assumption_ids: list[str]
    supporting_claim_ids: list[str]
    contradicting_claim_ids: list[str]
    equity_implication_direction: Literal["positive", "negative", "mixed", "unknown"]
    estimate_ids: list[str]
    quantification_status: Literal["quantified", "directional_only"]
    time_horizon: str
    weakening_observation: str
    central: bool = False
    broken_reason: str | None = None


class ReportContext(StrictModel):
    selected_premise: str
    factual_status: FactualStatus
    indian_equity_focus: str
    graph: CausalGraph
    central_case: Case
    material_alternatives: list[Case]
    assumptions: list[Assumption]
    accepted_claims: list[EvidenceClaim]
    contradicting_claims: list[EvidenceClaim]
    estimates: list[Estimate]
    challenge_findings: list[ChallengeFinding]
    adjudication_decisions: list[AdjudicationDecision]
    known_gaps: list[str]
    research_failures: list[str]
    sources: list[SourceRecord]


class NewsletterReport(StrictModel):
    headline: NonEmpty
    dek: NonEmpty
    why_this_matters: NonEmpty
    article_markdown: NonEmpty
    central_case_summary: NonEmpty
    key_assumptions: list[str] = Field(max_length=MAX_GENERATED_ITEMS["notes"])
    what_changes_the_view: list[str] = Field(max_length=MAX_GENERATED_ITEMS["notes"])
    source_ids_used: list[str] = Field(max_length=MAX_GENERATED_ITEMS["ids"])


class ModelCallRecord(StrictModel):
    id: str
    run_id: str
    stage: str
    model_name: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    retry_count: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class CandidateSelection(StrictModel):
    candidates: list[CandidateSeed] = Field(max_length=MAX_GENERATED_ITEMS["candidates"])


class ResearchTaskList(StrictModel):
    tasks: list[ResearchTask] = Field(max_length=MAX_GENERATED_ITEMS["tasks"])


class EvidenceClaimDraft(StrictModel):
    source_id: str
    claim: str
    exact_passage: str
    claim_type: Literal["fact", "estimate", "forecast", "inference", "assumption"]
    stance: Literal["supports", "contradicts", "context"]
    concepts: list[str] = Field(default_factory=list)
    geography: str | None = None
    time_horizon: str | None = None


class EvidenceClaimDrafts(StrictModel):
    claims: list[EvidenceClaimDraft] = Field(max_length=MAX_GENERATED_ITEMS["claims"])


class ChallengeResult(StrictModel):
    findings: list[ChallengeFinding] = Field(max_length=MAX_GENERATED_ITEMS["findings"])


class AdjudicationResult(StrictModel):
    decisions: list[AdjudicationDecision] = Field(max_length=MAX_GENERATED_ITEMS["findings"])


class CaseSelection(StrictModel):
    central_case: Case
    material_alternatives: list[Case] = Field(default_factory=list, max_length=MAX_GENERATED_ITEMS["cases"])
    broken_paths: list[Case] = Field(default_factory=list, max_length=MAX_GENERATED_ITEMS["cases"])
