"""Standalone data models for the knowledge_graph package.

No dependency on any external domain package. Any system can use these types
directly to build or query a knowledge graph.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# Common relation string constants — not enforced, just documented defaults.
# Callers may use any string as a relation.
PREREQUISITE_OF = "PREREQUISITE_OF"
COMPONENT_OF = "COMPONENT_OF"
CONTRASTS_WITH = "CONTRASTS_WITH"
APPLIES_TO = "APPLIES_TO"
RELATES_TO = "RELATES_TO"
IS_A = "IS_A"
PART_OF = "PART_OF"
CAUSES = "CAUSES"
DEFINED_BY = "DEFINED_BY"


class ReviewStatus(str, Enum):
    """Review state for identity assertions and proposals."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class IdentityRelation(str, Enum):
    """Assertions that may participate in identity-aware retrieval."""

    ALIAS_OF = "ALIAS_OF"
    SAME_AS = "SAME_AS"
    RELATED_TO = "RELATED_TO"


class ClaimStatus(str, Enum):
    """Lifecycle state of an assertion without deleting its history."""

    CURRENT = "current"
    SUPERSEDED = "superseded"
    DISPUTED = "disputed"
    RETRACTED = "retracted"


class KGNode(BaseModel):
    """A concept node in the knowledge graph."""

    id: str
    canonical_name: str
    domain: str = "general"
    fields: list[str] = Field(default_factory=list)
    external_ids: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KGEdge(BaseModel):
    """A typed directed edge between two nodes."""

    id: str
    subject_id: str
    subject_name: Optional[str] = None
    subject_domain: Optional[str] = None
    relation: str          # free-form string, e.g. "PREREQUISITE_OF"
    object_id: str
    object_name: Optional[str] = None
    object_domain: Optional[str] = None
    source: Optional[str] = None   # provenance — document id, URL, etc.
    source_hash: Optional[str] = None
    sources: list[str] = Field(default_factory=list)
    source_hashes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class IdentityLink(BaseModel):
    """A non-destructive identity, alias, or relatedness assertion."""

    id: str
    source_id: str
    target_id: str
    relation: IdentityRelation
    status: ReviewStatus = ReviewStatus.PENDING
    provenance: list[str] = Field(default_factory=list)
    field: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None


class IdentityProposal(BaseModel):
    """Auditable proposal produced by a chat, extractor, or resolver."""

    id: str
    source_id: str
    target_id: str
    relation: IdentityRelation
    rationale: str
    provenance: list[str] = Field(default_factory=list)
    status: ReviewStatus = ReviewStatus.PENDING
    proposed_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MatchCandidate(BaseModel):
    """A resolver candidate; candidates never imply automatic identity."""

    node: KGNode
    match_type: str
    score: float = Field(ge=0.0, le=1.0)
    deterministic: bool = False
    explanation: str


class Claim(BaseModel):
    """A time-indexed assertion that remains available after correction."""

    id: str
    subject_id: str
    predicate: str
    object_id: Optional[str] = None
    object_text: Optional[str] = None
    source: str
    source_version: Optional[str] = None
    fields: list[str] = Field(default_factory=list)
    observed_at: Optional[datetime] = None
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_quality: Optional[str] = None
    status: ClaimStatus = ClaimStatus.CURRENT


@dataclass
class Triplet:
    """A (subject, relation, object) fact candidate extracted from text."""

    subject: str   # concept name
    relation: str  # relation label (UPPER_SNAKE_CASE by convention)
    object: str    # concept name
    source: Optional[str] = None


@dataclass
class IngestDocument:
    """A document to extract triplets from and store in the knowledge graph.

    Parameters
    ----------
    id:
        Stable caller-supplied identifier used for provenance tracking.
    text:
        Raw text to extract triplets from.
    domain:
        Subject area (e.g. "finance", "medicine", "general"). Applied to all
        nodes created from this document.
    source:
        Optional human-readable provenance string (URL, file path, title).
        Stored on edges for traceability.
    metadata:
        Arbitrary key-value pairs for caller use (not stored in Neo4j).
    """

    id: str
    text: str
    domain: str = "general"
    source: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestResult:
    """Summary of a completed ingestion run."""

    total: int
    succeeded: int
    failed: int
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def __repr__(self) -> str:
        status = "ok" if self.ok else f"{self.failed} errors"
        return f"IngestResult(total={self.total}, succeeded={self.succeeded}, {status})"


@dataclass(frozen=True, repr=False)
class GraphHit:
    """A node returned from a graph traversal or search."""

    id: str
    canonical_name: str
    domain: str

    def __repr__(self) -> str:
        return f"GraphHit(id={self.id!r}, name={self.canonical_name!r}, domain={self.domain!r})"
