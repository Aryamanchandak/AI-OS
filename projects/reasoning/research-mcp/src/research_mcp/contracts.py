"""All Pydantic data contracts. Frozen before any stage is coded."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    query: str
    source_tier: str
    fetched_via: str  # "semantic_scholar"|"arxiv"|"wikipedia"|"brave"|"google_books"


class SourceRecord(BaseModel):
    source: str
    external_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    published: Optional[str] = None  # ISO date or year string
    url: Optional[str] = None
    raw_excerpt: str = ""
    content_hash: Optional[str] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    provenance: Provenance


class LogicalSource(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    fingerprint: str
    external_ids: dict[str, str] = Field(default_factory=dict)  # source -> external_id
    title: str
    authors: list[str] = Field(default_factory=list)
    published: Optional[str] = None
    url: Optional[str] = None
    raw_excerpt: str = ""
    provenance: list[Provenance] = Field(default_factory=list)


class TriageResult(BaseModel):
    correctness: Literal["true", "false", "topic"]
    effort: Literal["silent", "light", "deep"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class Annotation(BaseModel):
    logical_source_id: str
    relevance: float = Field(ge=0.0, le=1.0)
    key_findings: list[str] = Field(default_factory=list)
    credibility_tier: str


class ModelCallRecord(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model: str
    stage: Literal["triage", "expansion", "annotation", "synthesis", "correction", "claim_split"]
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    run_id: str
    status: Literal["success", "error"] = "success"


class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mode: Literal["research", "verify"]
    input: str
    status: Literal["pending", "running", "complete", "failed"] = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    cost_usd: float = 0.0
    model_calls: list[ModelCallRecord] = Field(default_factory=list)


class ResearchResult(BaseModel):
    run_id: str
    essay_path: str
    logical_sources: list[LogicalSource]
    cost_usd: float


class ClaimVerdict(BaseModel):
    claim_text: str
    verdict: Literal["supported", "contradicted", "mixed", "insufficient"]
    confidence: float = Field(ge=0.0, le=1.0)
    run_id: str


class SurfacedItem(BaseModel):
    claim_text: str
    triage: TriageResult
    essay_path: Optional[str] = None
    logical_sources: list[LogicalSource] = Field(default_factory=list)


class BriefReview(BaseModel):
    surfaced: list[SurfacedItem]
    passed_count: int
    run_id: str
