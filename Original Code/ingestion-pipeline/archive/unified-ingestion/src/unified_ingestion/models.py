from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AccessPolicy(BaseModel):
    classification: Literal["private", "shared", "public"] = "private"
    allowed_consumers: list[str] = Field(default_factory=lambda: ["kg", "vector"])

    @field_validator("allowed_consumers")
    @classmethod
    def validate_consumers(cls, values: list[str]) -> list[str]:
        cleaned = sorted(set(value.strip().lower() for value in values if value.strip()))
        if any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value) for value in cleaned):
            raise ValueError("Consumer names may contain only letters, digits, '_' and '-'")
        return cleaned


class EvidenceRef(BaseModel):
    source_record_id: str
    quote: str = Field(min_length=1)
    normalized_char_start: int | None = Field(default=None, ge=0)
    normalized_char_end: int | None = Field(default=None, ge=0)


class CaptureRequest(BaseModel):
    source_type: str = Field(min_length=1, max_length=64)
    origin: str = Field(min_length=1, max_length=2048)
    content: str | bytes
    captured_at: datetime = Field(default_factory=utc_now)
    observed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    access_policy: AccessPolicy = Field(default_factory=AccessPolicy)
    legacy_source_id: str | None = None

    @field_validator("source_type")
    @classmethod
    def normalize_source_type(cls, value: str) -> str:
        normalized = value.strip().lower().replace(" ", "_")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", normalized):
            raise ValueError("source_type may contain only letters, digits, '_' and '-'")
        return normalized


class ConceptProposal(BaseModel):
    proposal_id: str
    label: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["proposed", "approved", "rejected"] = "proposed"
    source_record_id: str
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ClaimProposal(BaseModel):
    proposal_id: str
    text: str = Field(min_length=1)
    concept_labels: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["current", "superseded", "disputed", "proposed"] = "proposed"
    source_record_id: str
    evidence: list[EvidenceRef] = Field(default_factory=list)


class RelationProposal(BaseModel):
    proposal_id: str
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["proposed", "approved", "rejected"] = "proposed"
    source_record_id: str
    evidence: list[EvidenceRef] = Field(default_factory=list)


class SemanticExtraction(BaseModel):
    concepts: list[ConceptProposal] = Field(default_factory=list)
    claims: list[ClaimProposal] = Field(default_factory=list)
    relations: list[RelationProposal] = Field(default_factory=list)
    field_tags: list[str] = Field(default_factory=list)
    source_quality_signals: list[str] = Field(default_factory=list)


class IngestionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    source_record_id: str
    canonical_record_id: str
    source_type: str
    origin: str
    normalized_origin: str
    captured_at: datetime
    observed_at: datetime | None
    raw_content_ref: str
    raw_content_hash: str
    normalized_content_hash: str
    version: int = Field(ge=1)
    supersedes_record_id: str | None = None
    source_status: Literal["current", "superseded", "disputed"] = "current"
    metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_metadata: dict[str, Any] = Field(default_factory=dict)
    access_policy: AccessPolicy
    normalization_version: str = "structural_normalization_v1"
    extraction_version: str
    semantic: SemanticExtraction = Field(default_factory=SemanticExtraction)
    confidence: float = Field(ge=0.0, le=1.0)
    review_status: Literal["not_required", "pending", "approved", "rejected"]
    created_at: datetime = Field(default_factory=utc_now)


class CaptureOutcome(BaseModel):
    source_record_id: str
    canonical_record_id: str
    capture_id: str
    raw_content_hash: str
    normalized_content_hash: str
    version: int
    exact_duplicate: bool
    normalized_duplicate: bool
    supersedes_record_id: str | None = None
    raw_content_ref: str


class ProcessOutcome(BaseModel):
    source_record_id: str
    envelope_id: str | None = None
    status: Literal[
        "processed", "review_pending", "rejected", "already_processed", "quarantined"
    ]
    dispatched_targets: list[str] = Field(default_factory=list)


class DispatchResult(BaseModel):
    target: str
    status: Literal["done", "failed", "skipped"]
    artifact_ref: str | None = None
    error: str | None = None
