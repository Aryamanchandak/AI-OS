from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from unified_ingestion.config import IngestionConfig
from unified_ingestion.dispatch import JsonHandoffConsumer
from unified_ingestion.extraction import ExtractionResult
from unified_ingestion.models import (
    AccessPolicy,
    CaptureRequest,
    ClaimProposal,
    ConceptProposal,
    EvidenceRef,
    IngestionEnvelope,
    SemanticExtraction,
)
from unified_ingestion.normalization import MalformedSourceError
from unified_ingestion.pipeline import UnifiedIngestionPipeline


class FixtureExtractor:
    def __init__(self, confidence: float = 0.95, *, alias: bool = False) -> None:
        self.confidence = confidence
        self.alias = alias
        self.calls = 0

    def extract(
        self,
        *,
        source_record_id: str,
        normalized_content: str,
        metadata: dict,
    ) -> ExtractionResult:
        self.calls += 1
        assert normalized_content
        return ExtractionResult(
            semantic=SemanticExtraction(
                concepts=[
                    ConceptProposal(
                        proposal_id=f"concept-{source_record_id}",
                        label="Duration",
                        aliases=["DUR"] if self.alias else [],
                        confidence=self.confidence,
                        source_record_id=source_record_id,
                        evidence=[
                            EvidenceRef(
                                source_record_id=source_record_id,
                                quote=normalized_content.strip(),
                                normalized_char_start=0,
                                normalized_char_end=len(normalized_content.strip()),
                            )
                        ],
                    )
                ],
                claims=[
                    ClaimProposal(
                        proposal_id=f"claim-{source_record_id}",
                        text="Duration measures rate sensitivity.",
                        concept_labels=["Duration"],
                        confidence=self.confidence,
                        source_record_id=source_record_id,
                        evidence=[
                            EvidenceRef(
                                source_record_id=source_record_id,
                                quote=normalized_content.strip(),
                                normalized_char_start=0,
                                normalized_char_end=len(normalized_content.strip()),
                            )
                        ],
                    )
                ],
            ),
            confidence=self.confidence,
            review_reasons=["alias_or_identity_proposal"] if self.alias else [],
        )


class RecordingConsumer:
    def __init__(self, target: str, failures: int = 0) -> None:
        self.target = target
        self.failures = failures
        self.calls: list[IngestionEnvelope] = []

    def consume(self, envelope: IngestionEnvelope) -> str:
        self.calls.append(envelope)
        if self.failures:
            self.failures -= 1
            raise RuntimeError(f"{self.target} unavailable")
        return f"memory://{self.target}/{envelope.envelope_id}"


def config(tmp_path: Path) -> IngestionConfig:
    return IngestionConfig(database_root=tmp_path / "Database")


def test_capture_is_immutable_and_exact_duplicate_is_linked(tmp_path: Path) -> None:
    with UnifiedIngestionPipeline(config(tmp_path)) as pipeline:
        request = CaptureRequest(source_type="note", origin="notes/duration.md", content="Duration")
        first = pipeline.capture(request)
        second = pipeline.capture(request)

        assert first.source_record_id == second.source_record_id
        assert second.exact_duplicate is True
        assert len(list(pipeline.store.rows("source_records"))) == 1
        assert len(list(pipeline.store.rows("captures"))) == 2
        assert os.stat(first.raw_content_ref).st_mode & 0o222 == 0


def test_source_type_cannot_escape_raw_root(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        CaptureRequest(source_type="../../outside", origin="note", content="content")


def test_normalized_duplicate_links_to_canonical_without_reextracting(tmp_path: Path) -> None:
    extractor = FixtureExtractor()
    with UnifiedIngestionPipeline(config(tmp_path), extractor=extractor) as pipeline:
        first = pipeline.capture(
            CaptureRequest(source_type="note", origin="a.md", content="Line one\n")
        )
        second = pipeline.capture(
            CaptureRequest(source_type="note", origin="b.md", content="Line one   \r\n\r\n")
        )
        outcomes = pipeline.process_pending()

        assert second.normalized_duplicate is True
        assert second.canonical_record_id == first.source_record_id
        assert len(outcomes) == 1
        assert extractor.calls == 1


def test_format_only_capture_does_not_supersede_semantic_version(tmp_path: Path) -> None:
    with UnifiedIngestionPipeline(config(tmp_path), extractor=FixtureExtractor()) as pipeline:
        first = pipeline.capture(
            CaptureRequest(source_type="note", origin="same.md", content="* item\n")
        )
        formatting_only = pipeline.capture(
            CaptureRequest(source_type="note", origin="same.md", content="- item   \r\n\r\n")
        )
        changed = pipeline.capture(
            CaptureRequest(source_type="note", origin="same.md", content="- different item\n")
        )

        assert formatting_only.normalized_duplicate is True
        assert formatting_only.version == first.version
        assert formatting_only.supersedes_record_id is None
        assert pipeline.store.get_source(first.source_record_id)["source_status"] == "superseded"
        assert changed.version == 2
        assert changed.supersedes_record_id == first.source_record_id


def test_new_origin_version_supersedes_without_erasing_history(tmp_path: Path) -> None:
    extractor = FixtureExtractor()
    kg = RecordingConsumer("kg")
    vector = RecordingConsumer("vector")
    with UnifiedIngestionPipeline(
        config(tmp_path), extractor=extractor, consumers=[kg, vector]
    ) as pipeline:
        first = pipeline.capture(
            CaptureRequest(
                source_type="note",
                origin="notes/duration.md",
                content="Duration measures rate sensitivity.",
                legacy_source_id="legacy-duration-v1",
            )
        )
        first_processed = pipeline.process_pending()[0]
        second = pipeline.capture(
            CaptureRequest(
                source_type="note",
                origin="notes/duration.md",
                content="Modified duration estimates price sensitivity.",
            )
        )
        second_processed = pipeline.process_pending()[0]

        assert second.version == 2
        assert second.supersedes_record_id == first.source_record_id
        assert Path(first.raw_content_ref).exists()
        assert pipeline.store.get_source(first.source_record_id)["source_status"] == "superseded"
        prior_envelope = pipeline.store.get_envelope(first_processed.envelope_id or "")
        assert prior_envelope is not None
        assert prior_envelope.source_status == "superseded"
        assert prior_envelope.semantic.claims[0].status == "superseded"
        assert kg.calls[1].supersedes_record_id == first.source_record_id
        assert vector.calls[1].source_record_id == second.source_record_id
        assert pipeline.store.resolve_legacy_reference("legacy-duration-v1") == first.source_record_id
        assert first_processed.dispatched_targets == ["kg", "vector"]
        assert second_processed.dispatched_targets == ["kg", "vector"]


def test_review_gate_blocks_identity_proposal_until_approved(tmp_path: Path) -> None:
    extractor = FixtureExtractor(alias=True)
    kg = RecordingConsumer("kg")
    with UnifiedIngestionPipeline(config(tmp_path), extractor=extractor, consumers=[kg]) as pipeline:
        captured = pipeline.capture(
            CaptureRequest(source_type="note", origin="duration.md", content="Duration fact")
        )
        pending = pipeline.process_pending()[0]
        assert pending.status == "review_pending"
        assert kg.calls == []

        approved = pipeline.resolve_review(
            pending.envelope_id or "", approved=True, resolver="pytest"
        )
        replay = pipeline.resolve_review(
            pending.envelope_id or "", approved=True, resolver="pytest"
        )

        assert approved.status == "processed"
        assert replay.dispatched_targets == []
        assert len(kg.calls) == 1
        assert captured.source_record_id == kg.calls[0].source_record_id
        assert kg.calls[0].semantic.concepts[0].status == "approved"


def test_failed_dispatch_retries_without_duplicate_success(tmp_path: Path) -> None:
    extractor = FixtureExtractor()
    kg = RecordingConsumer("kg", failures=1)
    with UnifiedIngestionPipeline(config(tmp_path), extractor=extractor, consumers=[kg]) as pipeline:
        captured = pipeline.capture(
            CaptureRequest(source_type="article", origin="https://example.com/a", content="A claim")
        )
        first = pipeline.process_pending()[0]
        second = pipeline.process_source(captured.source_record_id)
        third = pipeline.process_source(captured.source_record_id)

        dispatch = list(pipeline.store.rows("dispatches"))[0]
        assert first.dispatched_targets == []
        assert second.dispatched_targets == ["kg"]
        assert third.dispatched_targets == []
        assert dispatch["status"] == "done"
        assert dispatch["attempts"] == 2
        assert len(kg.calls) == 2


def test_access_policy_prevents_unauthorized_dispatch(tmp_path: Path) -> None:
    extractor = FixtureExtractor()
    kg = RecordingConsumer("kg")
    vector = RecordingConsumer("vector")
    with UnifiedIngestionPipeline(
        config(tmp_path), extractor=extractor, consumers=[kg, vector]
    ) as pipeline:
        pipeline.capture(
            CaptureRequest(
                source_type="note",
                origin="private.md",
                content="Private",
                access_policy=AccessPolicy(allowed_consumers=["kg"]),
            )
        )
        result = pipeline.process_pending()[0]
        assert result.dispatched_targets == ["kg"]
        assert vector.calls == []


def test_malformed_capture_is_quarantined(tmp_path: Path) -> None:
    with UnifiedIngestionPipeline(config(tmp_path)) as pipeline:
        with pytest.raises(MalformedSourceError):
            pipeline.capture(
                CaptureRequest(source_type="note", origin="bad.md", content=b"\xff")
            )
        assert len(list(pipeline.store.rows("quarantine"))) == 1
        assert len(list(pipeline.store.rows("source_records"))) == 0


def test_store_schema_is_explicit(tmp_path: Path) -> None:
    with UnifiedIngestionPipeline(config(tmp_path)) as pipeline:
        assert pipeline.store.table_names() == {
            "source_records",
            "captures",
            "envelopes",
            "review_queue",
            "dispatches",
            "quarantine",
            "legacy_references",
        }


def test_json_handoffs_share_envelope_and_provenance(tmp_path: Path) -> None:
    import json

    cfg = config(tmp_path)
    consumers = [
        JsonHandoffConsumer("kg", cfg.handoff_root),
        JsonHandoffConsumer("vector", cfg.handoff_root),
    ]
    with UnifiedIngestionPipeline(cfg, extractor=FixtureExtractor(), consumers=consumers) as pipeline:
        captured = pipeline.capture(
            CaptureRequest(source_type="note", origin="handoff.md", content="Duration")
        )
        result = pipeline.process_pending()[0]
        pipeline.process_source(captured.source_record_id)

        kg_files = list((cfg.handoff_root / "kg").glob("*.json"))
        vector_files = list((cfg.handoff_root / "vector").glob("*.json"))
        assert len(kg_files) == len(vector_files) == 1
        kg_payload = json.loads(kg_files[0].read_text(encoding="utf-8"))
        vector_payload = json.loads(vector_files[0].read_text(encoding="utf-8"))
        assert kg_payload["envelope"] == vector_payload["envelope"]
        assert kg_payload["provenance"]["source_record_id"] == captured.source_record_id
        assert result.envelope_id == kg_payload["envelope"]["envelope_id"]


def test_new_extraction_version_reprocesses_without_recapturing(tmp_path: Path) -> None:
    first_extractor = FixtureExtractor()
    cfg_v1 = IngestionConfig(
        database_root=tmp_path / "Database", extraction_version="extraction_v1"
    )
    with UnifiedIngestionPipeline(cfg_v1, extractor=first_extractor) as pipeline:
        captured = pipeline.capture(
            CaptureRequest(source_type="note", origin="versioned.md", content="Duration")
        )
        pipeline.process_pending()

    second_extractor = FixtureExtractor()
    cfg_v2 = IngestionConfig(
        database_root=tmp_path / "Database", extraction_version="extraction_v2"
    )
    with UnifiedIngestionPipeline(cfg_v2, extractor=second_extractor) as pipeline:
        results = pipeline.process_pending()
        assert len(results) == 1
        assert results[0].source_record_id == captured.source_record_id
        assert len(list(pipeline.store.rows("source_records"))) == 1
        assert len(list(pipeline.store.rows("envelopes"))) == 2
        assert second_extractor.calls == 1
