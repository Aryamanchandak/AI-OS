from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ingestion.routing import default_allowed_consumers


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AccessPolicy(BaseModel):
    classification: Literal["private", "shared", "public"] = "private"
    allowed_consumers: list[str] = Field(default_factory=default_allowed_consumers)

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


class UserSelection(BaseModel):
    """Producer-supplied boundary and its separately stored parent context."""

    context_text: str | None = None
    parent_source_ref: str = Field(min_length=1, max_length=4096)
    parent_start_char: int = Field(ge=0)
    parent_end_char: int = Field(gt=0)
    # Used only for bounded contextual vectorization of a fragment selection.
    # It never becomes evidence and is never merged into highlight_text.
    containing_sentence: str | None = None
    # When several selections share one captured parent, these locate this
    # selection inside that captured content.  A legacy single-selection
    # request omits them because its whole content is the selected span.
    source_start_char: int | None = Field(default=None, ge=0)
    source_end_char: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> "UserSelection":
        if self.parent_end_char <= self.parent_start_char:
            raise ValueError("parent_end_char must be greater than parent_start_char")
        if (self.source_start_char is None) != (self.source_end_char is None):
            raise ValueError(
                "source_start_char and source_end_char must be supplied together"
            )
        if (
            self.source_start_char is not None
            and self.source_end_char is not None
            and self.source_end_char <= self.source_start_char
        ):
            raise ValueError("source_end_char must be greater than source_start_char")
        return self


class CaptureRequest(BaseModel):
    source_type: str = Field(min_length=1, max_length=64)
    origin: str = Field(min_length=1, max_length=2048)
    content: str | bytes
    captured_at: datetime = Field(default_factory=utc_now)
    observed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    access_policy: AccessPolicy = Field(default_factory=AccessPolicy)
    boundary_origin: Literal["document_segment", "user_selection"] = "document_segment"
    user_selection: UserSelection | None = None
    user_selections: list[UserSelection] | None = None

    @field_validator("source_type")
    @classmethod
    def normalize_source_type(cls, value: str) -> str:
        normalized = value.strip().lower().replace(" ", "_")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", normalized):
            raise ValueError("source_type may contain only letters, digits, '_' and '-'")
        return normalized

    @model_validator(mode="after")
    def validate_boundary_origin(self) -> "CaptureRequest":
        has_single = self.user_selection is not None
        has_many = bool(self.user_selections)
        if self.boundary_origin == "user_selection" and has_single == has_many:
            raise ValueError(
                "user_selection inputs require exactly one of user_selection or "
                "non-empty user_selections"
            )
        if self.boundary_origin == "document_segment" and (has_single or has_many):
            raise ValueError(
                "selection details are only valid for user_selection inputs"
            )
        if has_many:
            assert self.user_selections is not None
            if any(
                item.source_start_char is None or item.source_end_char is None
                for item in self.user_selections
            ):
                raise ValueError(
                    "every item in user_selections requires source character offsets"
                )
        return self


class ConceptProposal(BaseModel):
    proposal_id: str
    label: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    model_confidence: float = Field(
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("model_confidence", "confidence"),
    )
    status: Literal["proposed", "approved", "rejected"] = "proposed"
    source_record_id: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    domain: str | None = None

    @property
    def confidence(self) -> float:
        """Compatibility view; the stored field is explicitly model-reported."""
        return self.model_confidence


class ClaimProposal(BaseModel):
    proposal_id: str
    text: str = Field(min_length=1)
    concept_labels: list[str] = Field(default_factory=list)
    model_confidence: float = Field(
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("model_confidence", "confidence"),
    )
    status: Literal[
        "current", "superseded", "disputed", "proposed", "retracted"
    ] = "proposed"
    source_record_id: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @property
    def confidence(self) -> float:
        """Compatibility view; the stored field is explicitly model-reported."""
        return self.model_confidence


class RelationProposal(BaseModel):
    proposal_id: str
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    model_confidence: float = Field(
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("model_confidence", "confidence"),
    )
    status: Literal["proposed", "approved", "rejected"] = "proposed"
    source_record_id: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    domain: str | None = None
    # Set only when the document explicitly asserts a strict, non-cyclic
    # hierarchy for this specific relation instance (e.g. "X is a prerequisite
    # of Y") — never inferred from the predicate name alone (T8). Gates cycle
    # detection in kg_consumer; a rejected cyclic edge is filed as a
    # CycleConflict for human review rather than silently dropped.
    hierarchical: bool = False

    @property
    def confidence(self) -> float:
        """Compatibility view; the stored field is explicitly model-reported."""
        return self.model_confidence


class SemanticExtraction(BaseModel):
    concepts: list[ConceptProposal] = Field(default_factory=list)
    claims: list[ClaimProposal] = Field(default_factory=list)
    relations: list[RelationProposal] = Field(default_factory=list)
    field_tags: list[str] = Field(default_factory=list)
    source_quality_signals: list[str] = Field(default_factory=list)


class ReviewSignal(BaseModel):
    """A deterministic explanation for why an envelope or proposal needs review."""

    code: str = Field(min_length=1)
    scope: Literal["envelope", "proposal"]
    proposal_id: str | None = None
    proposal_type: Literal["concept", "claim", "relation"] | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "ReviewSignal":
        if self.scope == "proposal":
            if not self.proposal_id or self.proposal_type is None:
                raise ValueError("proposal-scoped signals require proposal_id and proposal_type")
        elif self.proposal_id is not None or self.proposal_type is not None:
            raise ValueError("envelope-scoped signals cannot identify a proposal")
        return self


class ProposalReviewDecision(BaseModel):
    """One human decision, retained separately for each semantic proposal."""

    proposal_id: str = Field(min_length=1)
    action: Literal["approve", "reject", "edit"]
    edited_proposal: dict[str, Any] | None = None
    note: str = ""

    @model_validator(mode="after")
    def validate_edit(self) -> "ProposalReviewDecision":
        if self.action == "edit" and self.edited_proposal is None:
            raise ValueError("edited_proposal is required when action is edit")
        if self.action != "edit" and self.edited_proposal is not None:
            raise ValueError("edited_proposal is only valid when action is edit")
        return self


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
    # The three `*_content_*` fields above always describe the whole parent
    # document (provenance + tamper-check). The `highlight_*` fields below
    # carry this envelope's own unit of work — one highlight, not the document.
    highlight_index: int = Field(ge=0)
    highlight_text: str = Field(min_length=1)
    highlight_context_text: str | None = None
    highlight_start_char: int = Field(ge=0)
    highlight_end_char: int = Field(ge=0)
    highlight_boundary_origin: Literal["document_segment", "user_selection"] = (
        "document_segment"
    )
    highlight_parent_source_ref: str | None = None
    highlight_parent_start_char: int | None = Field(default=None, ge=0)
    highlight_parent_end_char: int | None = Field(default=None, ge=0)
    highlight_containing_sentence: str | None = None
    version: int = Field(ge=1)
    supersedes_record_id: str | None = None
    # How many highlights the superseded document was parsed into, so a
    # consumer can regenerate the predecessor's highlight ids and purge them.
    # Set together with `supersedes_record_id` or left None.
    supersedes_highlight_count: int | None = Field(default=None, ge=0)
    source_status: Literal["current", "superseded", "disputed"] = "current"
    metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_metadata: dict[str, Any] = Field(default_factory=dict)
    access_policy: AccessPolicy
    normalization_version: str = "structural_normalization_v1"
    extraction_version: str
    semantic: SemanticExtraction = Field(default_factory=SemanticExtraction)
    model_confidence: float = Field(
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("model_confidence", "confidence"),
    )
    review_policy_version: str = "deterministic_review_v1"
    review_signals: list[ReviewSignal] = Field(default_factory=list)
    review_status: Literal["not_required", "pending", "approved", "rejected"]
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_highlight_span(self) -> "IngestionEnvelope":
        if self.highlight_end_char <= self.highlight_start_char:
            raise ValueError("highlight_end_char must be greater than highlight_start_char")
        if self.supersedes_record_id is None and self.supersedes_highlight_count is not None:
            raise ValueError(
                "supersedes_highlight_count is only meaningful with supersedes_record_id"
            )
        parent_fields = (
            self.highlight_parent_source_ref,
            self.highlight_parent_start_char,
            self.highlight_parent_end_char,
        )
        if self.highlight_boundary_origin == "user_selection":
            if any(value is None for value in parent_fields):
                raise ValueError(
                    "user selections require a parent source reference and offsets"
                )
            assert self.highlight_parent_start_char is not None
            assert self.highlight_parent_end_char is not None
            if self.highlight_parent_end_char <= self.highlight_parent_start_char:
                raise ValueError(
                    "highlight_parent_end_char must exceed highlight_parent_start_char"
                )
        elif any(value is not None for value in parent_fields) or (
            self.highlight_containing_sentence is not None
        ):
            raise ValueError(
                "parent selection fields are only valid for user selections"
            )
        return self

    @property
    def confidence(self) -> float:
        """Compatibility view; the stored field is explicitly model-reported."""
        return self.model_confidence


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
    # None only for document-scoped outcomes that never reached a highlight
    # (a quarantined source, or a document with nothing parseable in it).
    highlight_index: int | None = Field(default=None, ge=0)
    envelope_id: str | None = None
    status: Literal[
        "processed",
        "review_pending",
        "rejected",
        "already_processed",
        "quarantined",
        "parse_failed",
        "extraction_failed",
        "empty_parse",
    ]
    dispatched_targets: list[str] = Field(default_factory=list)


class DispatchResult(BaseModel):
    target: str
    status: Literal["done", "failed", "skipped"]
    artifact_ref: str | None = None
    error: str | None = None
