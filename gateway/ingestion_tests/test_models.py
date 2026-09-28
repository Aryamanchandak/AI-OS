from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from gateway.ingestion.models import (
    AccessPolicy,
    ClaimProposal,
    ConceptProposal,
    IngestionEnvelope,
    RelationProposal,
)


def test_claim_proposal_supports_temporal_fields_and_retracted_status() -> None:
    observed_at = datetime(2026, 7, 20, 10, 30, tzinfo=timezone.utc)
    valid_from = datetime(2026, 7, 1, tzinfo=timezone.utc)
    valid_to = datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc)

    claim = ClaimProposal(
        proposal_id="claim-1",
        text="Duration measures rate sensitivity.",
        confidence=0.95,
        status="retracted",
        source_record_id="source-1",
        observed_at=observed_at,
        valid_from=valid_from,
        valid_to=valid_to,
    )

    assert claim.status == "retracted"
    assert claim.observed_at == observed_at
    assert claim.valid_from == valid_from
    assert claim.valid_to == valid_to


def test_concept_and_relation_proposals_support_optional_domain() -> None:
    concept = ConceptProposal(
        proposal_id="concept-1",
        label="Duration",
        confidence=0.9,
        source_record_id="source-1",
        domain="fixed_income",
    )
    relation = RelationProposal(
        proposal_id="relation-1",
        subject="Duration",
        predicate="MEASURES",
        object="Rate sensitivity",
        confidence=0.9,
        source_record_id="source-1",
        domain="fixed_income",
    )

    assert concept.domain == "fixed_income"
    assert relation.domain == "fixed_income"
    assert concept.model_confidence == concept.confidence == 0.9
    assert "model_confidence" in concept.model_dump()
    assert "confidence" not in concept.model_dump()


def test_envelope_keeps_freeform_metadata_and_forbids_chunks() -> None:
    fields = dict(
        envelope_id="envelope-1",
        source_record_id="source-1",
        canonical_record_id="canonical-1",
        source_type="markdown",
        origin="/vault/note.md",
        normalized_origin="/vault/note.md",
        captured_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        observed_at=None,
        raw_content_ref="bronze/source-1.md",
        raw_content_hash="raw-hash",
        normalized_content_hash="normalized-hash",
        highlight_index=0,
        highlight_text="One highlight of the note.",
        highlight_start_char=0,
        highlight_end_char=26,
        version=1,
        metadata={
            "arbitrary_nested_value": {"page": 17, "labels": ["one", "two"]}
        },
        access_policy=AccessPolicy(),
        extraction_version="empty-v1",
        confidence=1.0,
        review_status="not_required",
    )

    envelope = IngestionEnvelope(**fields)
    assert envelope.metadata["arbitrary_nested_value"]["page"] == 17
    assert "chunks" not in IngestionEnvelope.model_fields

    with pytest.raises(ValidationError):
        IngestionEnvelope(**fields, chunks=[])
