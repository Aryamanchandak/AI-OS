from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from unified_ingestion.models import (
    ClaimProposal,
    ConceptProposal,
    EvidenceRef,
    RelationProposal,
    SemanticExtraction,
)


class ExtractionResult(BaseModel):
    semantic: SemanticExtraction
    confidence: float = Field(ge=0.0, le=1.0)
    review_reasons: list[str] = Field(default_factory=list)


class SemanticExtractor(Protocol):
    def extract(
        self,
        *,
        source_record_id: str,
        normalized_content: str,
        metadata: dict[str, Any],
    ) -> ExtractionResult: ...


class _RawConcept(BaseModel):
    label: str
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quote: str | None = None


class _RawClaim(BaseModel):
    text: str
    concept_labels: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quote: str = Field(min_length=1)


class _RawRelation(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quote: str = Field(min_length=1)


class _RawExtraction(BaseModel):
    concepts: list[_RawConcept] = Field(default_factory=list)
    claims: list[_RawClaim] = Field(default_factory=list)
    relations: list[_RawRelation] = Field(default_factory=list)
    field_tags: list[str] = Field(default_factory=list)
    source_quality_signals: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)


class GatewayExtractionError(RuntimeError):
    pass


class GatewaySemanticExtractor:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8107",
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 180.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def _chat(self, prompt: str) -> dict[str, Any]:
        response_format = {
            "type": "json_schema",
            "name": "unified_ingestion_extraction",
            "strict": True,
            "schema": _RawExtraction.model_json_schema(),
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat",
            data=json.dumps(
                {
                    "prompt": prompt,
                    "model": self.model,
                    "temperature": 0.0,
                    "max_tokens": 4000,
                    "response_format": response_format,
                }
            ).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise GatewayExtractionError(f"Semantic extraction gateway call failed: {exc}") from exc
        parsed = payload.get("parsed")
        if parsed is None:
            try:
                parsed = json.loads(str(payload.get("text", "")))
            except json.JSONDecodeError as exc:
                raise GatewayExtractionError("Gateway returned no valid structured extraction") from exc
        if not isinstance(parsed, dict):
            raise GatewayExtractionError("Gateway extraction was not a JSON object")
        return parsed

    def extract(
        self,
        *,
        source_record_id: str,
        normalized_content: str,
        metadata: dict[str, Any],
    ) -> ExtractionResult:
        prompt = f"""You extract semantic proposals from source material for a shared knowledge system.

Return strict JSON matching the supplied schema. Concepts, claims, relations, aliases, and tags are
proposals only. Do not silently merge aliases or concepts. Confidence must reflect uncertainty.
Every claim must be supported by the source. Flag contradictions or low-quality evidence under
source_quality_signals. For every claim and relation, return an evidence_quote copied verbatim from
the normalized source. Concept evidence_quote is optional but must also be verbatim when present.

Metadata:
{json.dumps(metadata, sort_keys=True, default=str)}

Source:
{normalized_content}
"""
        try:
            raw = _RawExtraction.model_validate(self._chat(prompt))
        except ValidationError as exc:
            raise GatewayExtractionError(f"Structured extraction failed validation: {exc}") from exc

        def proposal_id(kind: str, index: int, value: str) -> str:
            return str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"ingestion:{source_record_id}:{kind}:{index}:{value.casefold()}",
                )
            )

        unresolved_evidence = False

        def evidence(quote: str | None) -> list[EvidenceRef]:
            nonlocal unresolved_evidence
            if not quote:
                return []
            start = normalized_content.find(quote)
            if start < 0:
                unresolved_evidence = True
                return [EvidenceRef(source_record_id=source_record_id, quote=quote)]
            return [
                EvidenceRef(
                    source_record_id=source_record_id,
                    quote=quote,
                    normalized_char_start=start,
                    normalized_char_end=start + len(quote),
                )
            ]

        semantic = SemanticExtraction(
            concepts=[
                ConceptProposal(
                    proposal_id=proposal_id("concept", index, item.label),
                    label=item.label,
                    aliases=item.aliases,
                    confidence=item.confidence,
                    source_record_id=source_record_id,
                    evidence=evidence(item.evidence_quote),
                )
                for index, item in enumerate(raw.concepts)
            ],
            claims=[
                ClaimProposal(
                    proposal_id=proposal_id("claim", index, item.text),
                    text=item.text,
                    concept_labels=item.concept_labels,
                    confidence=item.confidence,
                    source_record_id=source_record_id,
                    evidence=evidence(item.evidence_quote),
                )
                for index, item in enumerate(raw.claims)
            ],
            relations=[
                RelationProposal(
                    proposal_id=proposal_id(
                        "relation", index, f"{item.subject}:{item.predicate}:{item.object}"
                    ),
                    subject=item.subject,
                    predicate=item.predicate,
                    object=item.object,
                    confidence=item.confidence,
                    source_record_id=source_record_id,
                    evidence=evidence(item.evidence_quote),
                )
                for index, item in enumerate(raw.relations)
            ],
            field_tags=raw.field_tags,
            source_quality_signals=raw.source_quality_signals,
        )
        reasons: list[str] = []
        if any(concept.aliases for concept in semantic.concepts):
            reasons.append("alias_or_identity_proposal")
        if raw.source_quality_signals:
            reasons.append("source_quality_signal")
        if unresolved_evidence:
            reasons.append("unresolved_evidence_quote")
        return ExtractionResult(
            semantic=semantic,
            confidence=raw.overall_confidence,
            review_reasons=reasons,
        )


class EmptySemanticExtractor:
    """Safe offline extractor: emits no beliefs and therefore requires review."""

    def extract(
        self,
        *,
        source_record_id: str,
        normalized_content: str,
        metadata: dict[str, Any],
    ) -> ExtractionResult:
        del source_record_id, normalized_content, metadata
        return ExtractionResult(
            semantic=SemanticExtraction(),
            confidence=0.0,
            review_reasons=["semantic_extractor_not_configured"],
        )
