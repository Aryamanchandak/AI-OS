"""SemanticExtractor backed by the LLM gateway's structured-output chat API.

All model traffic goes through `llm_gateway.client.LLM.chat()` (ground rule
R1 — no direct provider calls). Evidence is never trusted from the model's
own offsets: each returned quote is located in `normalized_content` by exact
string search after the fact, and dropped (not guessed at) if it doesn't
match verbatim.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ingestion.extraction.base import (
    ExtractionError,
    ExtractionResult,
    HighlightExtractionInput,
)
from ingestion.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    build_batch_extraction_prompt,
    build_extraction_prompt,
)
from ingestion.models import (
    ClaimProposal,
    ConceptProposal,
    EvidenceRef,
    RelationProposal,
    SemanticExtraction,
)

DEFAULT_MAX_TOKENS = 4096
# One batched call returns a full payload per highlight, so the output budget
# scales with the batch, not with one document. A highlight is at most
# ~512 words and its payload (concepts + claims + relations, each carrying
# verbatim quotes) runs to roughly 1.5k output tokens; at the default batch
# size of 4 that is ~6k, so 12288 leaves headroom rather than truncating —
# a truncated response fails schema validation and kills the whole batch.
DEFAULT_BATCH_MAX_TOKENS = 12288
EXTRACTION_CHAT_PROFILE = "knowledge-extraction-v1"


class ChatClient(Protocol):
    def chat(
        self,
        prompt: str | None = None,
        *,
        messages: list[dict[str, Any]] | None = None,
        system: Any = None,
        profile: str | None = None,
        provider: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        response_format: Any = None,
    ) -> dict[str, Any]: ...


class _ExtractedConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quotes: list[str] = Field(min_length=1)


class _ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    concept_labels: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quotes: list[str] = Field(min_length=1)


class _ExtractedRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quotes: list[str] = Field(min_length=1)
    hierarchical: bool = Field(
        default=False,
        description=(
            "True only if the document explicitly states this specific "
            "relation is a strict, non-cyclic hierarchy (e.g. a prerequisite "
            "or containment chain where a loop back would be a "
            "contradiction). Do not infer this from the predicate name alone."
        ),
    )


class _ExtractionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concepts: list[_ExtractedConcept] = Field(default_factory=list)
    claims: list[_ExtractedClaim] = Field(default_factory=list)
    relations: list[_ExtractedRelation] = Field(default_factory=list)
    field_tags: list[str] = Field(default_factory=list)
    source_quality_signals: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)


class _HighlightExtractionPayload(_ExtractionPayload):
    """One highlight's payload inside a batched response, tagged with its id."""

    batch_item_id: str = Field(min_length=1)


class _BatchExtractionPayload(BaseModel):
    """Wrapper object, not a bare array — structured output requires an object."""

    model_config = ConfigDict(extra="forbid")

    items: list[_HighlightExtractionPayload] = Field(default_factory=list)


def _locate_evidence(
    quote: str, *, source_record_id: str, normalized_content: str
) -> EvidenceRef | None:
    stripped = quote.strip()
    if not stripped:
        return None
    start = normalized_content.find(stripped)
    if start == -1:
        return None
    return EvidenceRef(
        source_record_id=source_record_id,
        quote=stripped,
        normalized_char_start=start,
        normalized_char_end=start + len(stripped),
    )


def _evidence_refs(
    quotes: list[str], *, source_record_id: str, normalized_content: str
) -> list[EvidenceRef]:
    refs = (
        _locate_evidence(
            quote, source_record_id=source_record_id, normalized_content=normalized_content
        )
        for quote in quotes
    )
    return [ref for ref in refs if ref is not None]


def _to_semantic_extraction(
    payload: _ExtractionPayload, *, source_record_id: str, normalized_content: str
) -> SemanticExtraction:
    concepts = [
        ConceptProposal(
            proposal_id=f"concept-{source_record_id}-{index}",
            label=item.label,
            aliases=item.aliases,
            confidence=item.confidence,
            source_record_id=source_record_id,
            evidence=_evidence_refs(
                item.evidence_quotes,
                source_record_id=source_record_id,
                normalized_content=normalized_content,
            ),
        )
        for index, item in enumerate(payload.concepts)
    ]
    claims = [
        ClaimProposal(
            proposal_id=f"claim-{source_record_id}-{index}",
            text=item.text,
            concept_labels=item.concept_labels,
            confidence=item.confidence,
            source_record_id=source_record_id,
            evidence=_evidence_refs(
                item.evidence_quotes,
                source_record_id=source_record_id,
                normalized_content=normalized_content,
            ),
        )
        for index, item in enumerate(payload.claims)
    ]
    relations = [
        RelationProposal(
            proposal_id=f"relation-{source_record_id}-{index}",
            subject=item.subject,
            predicate=item.predicate,
            object=item.object,
            confidence=item.confidence,
            source_record_id=source_record_id,
            evidence=_evidence_refs(
                item.evidence_quotes,
                source_record_id=source_record_id,
                normalized_content=normalized_content,
            ),
            hierarchical=item.hierarchical,
        )
        for index, item in enumerate(payload.relations)
    ]
    return SemanticExtraction(
        concepts=concepts,
        claims=claims,
        relations=relations,
        field_tags=payload.field_tags,
        source_quality_signals=payload.source_quality_signals,
    )


def _to_result(
    payload: _ExtractionPayload, *, source_record_id: str, normalized_content: str
) -> ExtractionResult:
    semantic = _to_semantic_extraction(
        payload,
        source_record_id=source_record_id,
        normalized_content=normalized_content,
    )
    has_semantic_output = bool(semantic.concepts or semantic.claims or semantic.relations)
    return ExtractionResult(
        semantic=semantic,
        # A model cannot be highly confident in an extraction that contains no
        # semantic output. The review policy independently blocks empty
        # results; this cap keeps the recorded confidence internally honest as
        # well.
        model_confidence=payload.overall_confidence if has_semantic_output else 0.0,
        review_reasons=[],
    )


class GatewayExtractor:
    """Real extraction through the LLM gateway, one highlight or a batch of them.

    Satisfies both `SemanticExtractor` (`extract`) and `BatchSemanticExtractor`
    (`extract_batch`). Extraction is the one paid model call in this pipeline,
    so the batched path is the one the pipeline uses: it covers several
    highlights per call instead of one call per highlight.
    """

    def __init__(
        self,
        *,
        chat_client: ChatClient,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        batch_max_tokens: int = DEFAULT_BATCH_MAX_TOKENS,
    ) -> None:
        self._client = chat_client
        self.max_tokens = max_tokens
        self.batch_max_tokens = batch_max_tokens

    def _chat(self, prompt: str, *, schema: dict[str, Any], max_tokens: int) -> Any:
        try:
            response = self._client.chat(
                prompt,
                system=EXTRACTION_SYSTEM_PROMPT,
                profile=EXTRACTION_CHAT_PROFILE,
                max_tokens=max_tokens,
                temperature=0.0,
                response_format={"type": "json_schema", "schema": schema},
            )
        except Exception as exc:
            raise ExtractionError(f"Gateway extraction call failed: {exc}") from exc

        parsed = response.get("parsed") if isinstance(response, dict) else None
        if parsed is None:
            raise ExtractionError("Gateway did not return structured output for extraction")
        return parsed

    def extract(
        self,
        *,
        source_record_id: str,
        normalized_content: str,
        metadata: dict[str, Any],
    ) -> ExtractionResult:
        del metadata
        parsed = self._chat(
            build_extraction_prompt(normalized_content),
            schema=_ExtractionPayload.model_json_schema(),
            max_tokens=self.max_tokens,
        )
        try:
            payload = _ExtractionPayload.model_validate(parsed)
        except ValidationError as exc:
            raise ExtractionError(f"Extraction payload failed schema validation: {exc}") from exc
        return _to_result(
            payload,
            source_record_id=source_record_id,
            normalized_content=normalized_content,
        )

    def extract_batch(
        self, items: list[HighlightExtractionInput]
    ) -> dict[str, ExtractionResult]:
        """Extract several highlights in one call, verified back onto their ids.

        The model is never trusted to have kept the batch straight. After schema
        validation, deterministic code checks that the returned set of
        `batch_item_id`s is exactly the set that went in — a missing,
        duplicated, or unrecognized id is a fail-loud `ExtractionError`, never a
        silent mismapping of one highlight's beliefs onto another's provenance.
        This is the same posture the evidence check already takes: verify
        structure in code, never on the model's word.
        """
        if not items:
            return {}
        by_id = {item.batch_item_id: item for item in items}
        if len(by_id) != len(items):
            raise ExtractionError("Batch contains duplicate batch_item_id values")

        parsed = self._chat(
            build_batch_extraction_prompt(items),
            schema=_BatchExtractionPayload.model_json_schema(),
            max_tokens=self.batch_max_tokens,
        )
        try:
            payload = _BatchExtractionPayload.model_validate(parsed)
        except ValidationError as exc:
            raise ExtractionError(
                f"Batched extraction payload failed schema validation: {exc}"
            ) from exc

        returned = [entry.batch_item_id for entry in payload.items]
        if len(returned) != len(set(returned)):
            raise ExtractionError("Batched extraction returned a duplicate batch_item_id")
        if set(returned) != set(by_id):
            missing = sorted(set(by_id) - set(returned))
            unexpected = sorted(set(returned) - set(by_id))
            raise ExtractionError(
                "Batched extraction did not return one payload per highlight "
                f"(missing={missing}, unexpected={unexpected})"
            )

        return {
            entry.batch_item_id: _to_result(
                entry,
                source_record_id=by_id[entry.batch_item_id].source_record_id,
                # Evidence is located in the highlight, never in its context:
                # the highlight is what this envelope is accountable for.
                normalized_content=by_id[entry.batch_item_id].highlight_text,
            )
            for entry in payload.items
        }
