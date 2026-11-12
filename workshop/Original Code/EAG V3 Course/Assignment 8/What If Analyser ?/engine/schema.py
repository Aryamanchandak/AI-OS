"""Dataclasses + structured-output schema for the extraction call.

No logic lives here. These types are the shared vocabulary for the whole
pipeline: extract.py builds a Graph, propagate.py resolves signs on it, and
synth.py reads outcome nodes off it.

Two representations live here:
- the mutable `@dataclass` types below are the internal pipeline vocabulary;
- the Pydantic `*In` models near the bottom are the schema Gemini fills in via
  structured JSON output (google-genai `response_schema`), then we copy them
  into the dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

# Type aliases make the causal vocabulary visible to readers. Runtime values are
# checked at the extraction boundary because these aliases are not validators.
Sign = int  # -1, 0, +1
Magnitude = str  # "low" | "med" | "high"
NodeType = str  # "intervention" | "intermediate" | "outcome"


@dataclass
class Node:
    """A causal variable and its scenario-specific resolved state."""

    # Identity and classification come from extraction.
    id: str  # "n1", "n2", ...
    label: str  # "INR spot", "corporate borrowing cost"
    node_type: NodeType

    # The remaining fields are defaults until propagate() resolves a scenario.
    sign: Sign = 0
    magnitude: Magnitude = "med"
    contested: bool = False
    # Human-readable evidence lines used by the audit UI and synthesizer.
    trace: list[str] = field(default_factory=list)


@dataclass
class Edge:
    """A directed causal relationship between two nodes."""

    src: str
    dst: str
    sign: Sign  # +1 = src up pushes dst up; -1 = inverse
    strength: Magnitude
    mechanism: str  # ONE sentence, why src moves dst
    # Research/debate fields deliberately have defaults so old hand-built
    # fixtures and the ungrounded fallback remain valid.
    confidence: Magnitude = "med"
    time_lag: str = "unspecified"
    conditions: list[str] = field(default_factory=list)
    evidence_status: str = "unverified"
    supporting_claim_ids: list[str] = field(default_factory=list)
    contradicting_claim_ids: list[str] = field(default_factory=list)


@dataclass
class Unknown:
    """A binary scenario choice that overrides one node during propagation."""

    id: str  # "u1", "u2"
    question: str  # "Does the RBI cut again in the next quarter?"
    affects_node_id: str  # which node this unknown sets the sign of


@dataclass
class Graph:
    """The complete extracted model shared by all pipeline stages."""

    nodes: list[Node]
    edges: list[Edge]
    unknowns: list[Unknown]  # exactly 2


@dataclass
class ResearchQueryGroup:
    """A bounded family of queries with an explicit evidentiary purpose."""

    theme: str
    intent: str  # "evidence" | "counterevidence" | "context"
    queries: list[str]


@dataclass
class ResearchPlan:
    """The planner's complete retrieval contract."""

    query_groups: list[ResearchQueryGroup]


@dataclass
class SourceRecord:
    """One fetched source and its deterministic ranking signals."""

    id: str
    url: str
    title: str
    publisher: str
    retrieved_at: str
    extracted_text: str
    source_type: str = "web"
    published_at: str | None = None
    authority: Magnitude = "low"
    recency: Magnitude = "low"
    relevance: Magnitude = "low"


@dataclass
class EvidenceClaim:
    """A source-linked claim; this list is the evidence ledger."""

    id: str
    text: str
    source_id: str
    supporting_passage: str
    claim_type: str  # "fact" | "forecast" | "inference" | "assumption"
    stance: str  # "supports" | "contradicts" | "context"
    confidence: Magnitude = "med"
    geography: str = ""
    time_horizon: str = ""
    concepts: list[str] = field(default_factory=list)


@dataclass
class CritiqueFinding:
    """One critic objection aimed at a named graph relationship."""

    id: str
    src: str
    dst: str
    issue: str
    recommendation: str
    severity: Magnitude
    claim_ids: list[str] = field(default_factory=list)


@dataclass
class GraphCritique:
    """Exactly one structured challenge, using one selected role."""

    role: str
    summary: str
    findings: list[CritiqueFinding]


@dataclass
class AdjudicationReport:
    """The one-round adjudicator's visible decision record."""

    accepted: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


@dataclass
class GraphDiff:
    """Deterministic comparison between builder and adjudicated graphs."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pydantic models used as Gemini's structured-output schema.
# Mirror the dataclasses above exactly. google-genai turns these into the
# response_schema and returns a parsed CausalGraphOut instance.
#
# Note on `sign`: Gemini's schema `enum` is effectively STRING-only, so we
# cannot pin it to {-1, 1} in the schema. We keep it a plain int and lean on
# the field description + the system prompt; extract._validate then rejects any
# stray value and the retry loop corrects it.
# ---------------------------------------------------------------------------


class NodeIn(BaseModel):
    """Model-facing schema for one graph node."""

    id: str = Field(description="n1, n2, ...")
    label: str = Field(
        description="Short noun phrase, e.g. 'corporate borrowing cost'."
    )
    node_type: Literal["intervention", "intermediate", "outcome"]


class EdgeIn(BaseModel):
    """Model-facing schema for one signed causal edge."""

    src: str
    dst: str
    sign: int = Field(
        description="+1 = src up pushes dst up; -1 = inverse. Only -1 or +1."
    )
    strength: Literal["low", "med", "high"]
    mechanism: str = Field(
        description="ONE sentence: why src moves dst. Never empty."
    )
    confidence: Literal["low", "med", "high"] = "med"
    time_lag: str = "unspecified"
    conditions: list[str] = Field(default_factory=list)
    evidence_status: Literal[
        "supported", "mixed", "contradicted", "assumption", "unverified"
    ] = "unverified"
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: list[str] = Field(default_factory=list)


class UnknownIn(BaseModel):
    """Model-facing schema for one binary uncertainty."""

    id: str = Field(description="u1, u2")
    question: str = Field(
        description="Binary yes/no question, e.g. 'Does oil hold above $90?'"
    )
    affects_node_id: str = Field(
        description="Node id whose sign this unknown sets."
    )


class CausalGraphOut(BaseModel):
    """The full extraction payload Gemini fills in.

    8-15 nodes (exactly one intervention, 3-5 outcomes, rest intermediate) and
    exactly 2 genuine binary unknowns a domain expert would argue about.
    """

    # Keeping these nested types explicit lets google-genai generate a strict
    # JSON response schema instead of asking the model for free-form prose.
    nodes: list[NodeIn]
    edges: list[EdgeIn]
    unknowns: list[UnknownIn]


class ResearchQueryGroupIn(BaseModel):
    """Structured-output schema for one related family of search queries."""

    theme: str
    intent: Literal["evidence", "counterevidence", "context"]
    queries: list[str]


class ResearchPlanOut(BaseModel):
    """Structured-output envelope returned by the research planner."""

    query_groups: list[ResearchQueryGroupIn]


class EvidenceClaimIn(BaseModel):
    """Model-facing evidence claim before local source validation and ID assignment."""

    text: str
    source_id: str
    supporting_passage: str
    claim_type: Literal["fact", "forecast", "inference", "assumption"]
    stance: Literal["supports", "contradicts", "context"]
    confidence: Literal["low", "med", "high"] = "med"
    geography: str = ""
    time_horizon: str = ""
    concepts: list[str] = Field(default_factory=list)


class EvidenceClaimsOut(BaseModel):
    """Structured-output envelope for a batch of extracted claims."""

    claims: list[EvidenceClaimIn]


class CritiqueFindingIn(BaseModel):
    """Model-facing criticism of one directed graph relationship."""

    src: str
    dst: str
    issue: str
    recommendation: str
    severity: Literal["low", "med", "high"]
    claim_ids: list[str] = Field(default_factory=list)


class GraphCritiqueOut(BaseModel):
    """Structured-output envelope for the single critic pass."""

    summary: str
    findings: list[CritiqueFindingIn]


class AdjudicationReportIn(BaseModel):
    """Model-facing record of accepted, changed, and unresolved objections."""

    accepted: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class AdjudicationOut(BaseModel):
    """Final repaired graph paired with its adjudication audit trail."""

    graph: CausalGraphOut
    report: AdjudicationReportIn


class EdgeEvidenceIn(BaseModel):
    """Verifier conclusion for one sensitivity-selected graph edge."""

    src: str
    dst: str
    evidence_status: Literal[
        "supported", "mixed", "contradicted", "assumption", "unverified"
    ]
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    explanation: str


class EdgeEvidenceOut(BaseModel):
    """Structured-output envelope for batched edge verification."""

    edges: list[EdgeEvidenceIn]
