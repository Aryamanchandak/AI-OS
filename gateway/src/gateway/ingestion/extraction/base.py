from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import AliasChoices, BaseModel, Field

from gateway.ingestion.models import SemanticExtraction


class ExtractionError(RuntimeError):
    pass


class ExtractionResult(BaseModel):
    semantic: SemanticExtraction
    model_confidence: float = Field(
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("model_confidence", "confidence"),
    )
    review_reasons: list[str] = Field(default_factory=list)

    @property
    def confidence(self) -> float:
        """Compatibility view for extractors that still emit `confidence`."""
        return self.model_confidence


class HighlightExtractionInput(BaseModel):
    """One highlight queued for extraction, with its place in a batch.

    `batch_item_id` is short and batch-local (`h0`, `h1`, ...) rather than a
    pair or a UUID: it is the token the model has to copy back for every
    payload, so it is cheap and hard to mistranscribe. It carries no meaning
    outside the single call it was minted for — the durable identity is
    `(source_record_id, highlight_index)`.
    """

    batch_item_id: str = Field(min_length=1)
    source_record_id: str
    highlight_index: int = Field(ge=0)
    highlight_text: str = Field(min_length=1)
    context_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticExtractor(Protocol):
    def extract(
        self,
        *,
        source_record_id: str,
        normalized_content: str,
        metadata: dict[str, Any],
    ) -> ExtractionResult: ...


@runtime_checkable
class BatchSemanticExtractor(Protocol):
    """An extractor that can cover several highlights in one model call.

    Optional. It is a separate protocol rather than a second method on
    `SemanticExtractor` because `SemanticExtractor` is structural and is
    satisfied today by plain classes that inherit nothing — a mixin would never
    reach them. `extract_highlights` below bridges the two, and
    `runtime_checkable` is what lets a caller ask "does this extractor batch?"
    without every extractor having to declare an answer.
    """

    def extract_batch(
        self, items: list[HighlightExtractionInput]
    ) -> dict[str, ExtractionResult]: ...


def extract_highlights(
    extractor: SemanticExtractor | BatchSemanticExtractor,
    items: list[HighlightExtractionInput],
) -> dict[str, ExtractionResult]:
    """Extract a batch of highlights, keyed by `batch_item_id`.

    Uses the extractor's own batching when it has any, and otherwise falls back
    to one `.extract()` call per highlight. The fallback is what keeps every
    single-highlight extractor — including `EmptySemanticExtractor` and the test
    fixtures — working unchanged now that the pipeline is batch-shaped.

    An `ExtractionError` from either path propagates: the caller decides what a
    failed batch means, and it must mean the same thing for every item in it.
    """
    if not items:
        return {}
    if isinstance(extractor, BatchSemanticExtractor):
        return extractor.extract_batch(items)
    return {
        item.batch_item_id: extractor.extract(
            source_record_id=item.source_record_id,
            normalized_content=item.highlight_text,
            metadata=item.metadata,
        )
        for item in items
    }


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
            model_confidence=0.0,
            review_reasons=["semantic_extractor_not_configured"],
        )
