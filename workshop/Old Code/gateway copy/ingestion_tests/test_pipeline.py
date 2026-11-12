from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from gateway.ingestion.config import IngestionConfig, SegmentationConfig
from gateway.ingestion.consumers.kg_consumer import KGConsumer
from gateway.ingestion.extraction.base import ExtractionError, ExtractionResult
from gateway.ingestion.models import (
    AccessPolicy,
    CaptureRequest,
    ClaimProposal,
    ConceptProposal,
    EvidenceRef,
    IngestionEnvelope,
    ProposalReviewDecision,
    RelationProposal,
    SemanticExtraction,
    UserSelection,
)
from gateway.ingestion.normalization import MalformedSourceError
from gateway.ingestion.parsing import HeadingTopicSegmenter
from gateway.ingestion.pipeline import UnifiedIngestionPipeline


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


class RelationFixtureExtractor:
    """Emits a single hierarchical relation, for edit round-trip coverage."""

    def extract(
        self,
        *,
        source_record_id: str,
        normalized_content: str,
        metadata: dict,
    ) -> ExtractionResult:
        assert normalized_content
        return ExtractionResult(
            semantic=SemanticExtraction(
                relations=[
                    RelationProposal(
                        proposal_id=f"relation-{source_record_id}",
                        subject="Duration",
                        predicate="is a prerequisite of",
                        object="Convexity",
                        confidence=0.95,
                        source_record_id=source_record_id,
                        hierarchical=True,
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
            confidence=0.95,
            # Forces review_status to "pending" so the proposal is actually
            # queued for review, exactly like FixtureExtractor's alias mode.
            review_reasons=["alias_or_identity_proposal"],
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


class RecordingKGStore:
    """A `KGStore` fake with no internal dedup -- every call is appended as-is.

    Used to prove T10's "re-dispatch = no-op" guarantee at the level it
    actually lives: the `Dispatcher`'s status-skip. If `Dispatcher` ever
    called `KGConsumer.consume()` twice for the same envelope+target, this
    store would show duplicated claims/edges, since it has no `MERGE`
    semantics of its own to paper over the bug.
    """

    def __init__(self) -> None:
        self.resolved: list[str] = []
        self.claims: list = []
        self.batched_edges: list = []

    def resolve_or_create_node(self, label, *, domain="general", node_id=None, external_ids=None, fields=None, highlight_id=None):
        from gateway.ingestion.kg.models import KGNode

        self.resolved.append(label)
        return KGNode(id=f"node:{label}", canonical_name=label, domain=domain), [], True

    def submit_identity_proposal(self, proposal) -> None:
        pass

    def submit_cycle_conflict(self, conflict) -> None:
        pass

    def upsert_edge(self, edge, *, check_cycle=False) -> None:
        self.batched_edges.append(edge)

    def upsert_edge_batch(self, edges) -> None:
        self.batched_edges.extend(edges)

    def upsert_claim(self, claim) -> None:
        self.claims.append(claim)

    def purge_contributions(self, highlight_id) -> None:
        pass


class EmptyHighConfidenceExtractor:
    def extract(
        self,
        *,
        source_record_id: str,
        normalized_content: str,
        metadata: dict,
    ) -> ExtractionResult:
        del source_record_id, normalized_content, metadata
        return ExtractionResult(
            semantic=SemanticExtraction(),
            confidence=0.99,
        )


class MissingConceptEvidenceExtractor:
    def extract(
        self,
        *,
        source_record_id: str,
        normalized_content: str,
        metadata: dict,
    ) -> ExtractionResult:
        del metadata
        return ExtractionResult(
            semantic=SemanticExtraction(
                concepts=[
                    ConceptProposal(
                        proposal_id=f"concept-{source_record_id}",
                        label="Duration",
                        confidence=0.99,
                        source_record_id=source_record_id,
                    )
                ],
                claims=[
                    ClaimProposal(
                        proposal_id=f"claim-{source_record_id}",
                        text="Duration measures rate sensitivity.",
                        confidence=0.99,
                        source_record_id=source_record_id,
                        evidence=[
                            EvidenceRef(
                                source_record_id=source_record_id,
                                quote=normalized_content.strip(),
                                normalized_char_start=1,
                                normalized_char_end=len(normalized_content.strip()),
                            )
                        ],
                    )
                ],
            ),
            confidence=0.99,
        )


class FlakyExtractor:
    """Raises ExtractionError for chosen sources / a fixed number of calls."""

    def __init__(self, *, fail_for: set[str] | None = None, fail_times: int = 0) -> None:
        self.fail_for = fail_for or set()
        self.fail_times = fail_times
        self.calls = 0

    def extract(
        self,
        *,
        source_record_id: str,
        normalized_content: str,
        metadata: dict,
    ) -> ExtractionResult:
        del metadata
        self.calls += 1
        if source_record_id in self.fail_for:
            raise ExtractionError(f"gateway unavailable for {source_record_id}")
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ExtractionError("gateway unavailable")
        stripped = normalized_content.strip()
        return ExtractionResult(
            semantic=SemanticExtraction(
                concepts=[
                    ConceptProposal(
                        proposal_id=f"concept-{source_record_id}",
                        label="Duration",
                        confidence=0.95,
                        source_record_id=source_record_id,
                        evidence=[
                            EvidenceRef(
                                source_record_id=source_record_id,
                                quote=stripped,
                                normalized_char_start=0,
                                normalized_char_end=len(stripped),
                            )
                        ],
                    )
                ],
            ),
            confidence=0.95,
        )


def config(tmp_path: Path) -> IngestionConfig:
    return IngestionConfig(
        database_root=tmp_path / "Database",
        segmentation=SegmentationConfig(mode="deterministic"),
    )


def test_capture_is_immutable_and_exact_duplicate_is_linked(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    with UnifiedIngestionPipeline(cfg) as pipeline:
        request = CaptureRequest(source_type="note", origin="notes/duration.md", content="Duration")
        first = pipeline.capture(request)
        second = pipeline.capture(request)

        assert first.source_record_id == second.source_record_id
        assert second.exact_duplicate is True
        assert Path(first.raw_content_ref) == (
            cfg.raw_root / f"{first.source_record_id}.md"
        )
        assert len(list(pipeline.store.rows("source_records"))) == 1
        assert len(list(pipeline.store.rows("captures"))) == 2
        assert os.stat(first.raw_content_ref).st_mode & 0o222 == 0


def test_source_type_cannot_escape_raw_root(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        CaptureRequest(source_type="../../outside", origin="note", content="content")


def test_untrusted_or_missing_origin_extension_falls_back_to_raw(
    tmp_path: Path,
) -> None:
    with UnifiedIngestionPipeline(config(tmp_path)) as pipeline:
        captured = pipeline.capture(
            CaptureRequest(
                source_type="article",
                origin="https://example.com/read?format=.md",
                content="content",
            )
        )

    assert Path(captured.raw_content_ref).suffix == ".raw"


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


def test_deterministic_review_blocks_empty_high_confidence_extraction(
    tmp_path: Path,
) -> None:
    kg = RecordingConsumer("kg")
    with UnifiedIngestionPipeline(
        config(tmp_path),
        extractor=EmptyHighConfidenceExtractor(),
        consumers=[kg],
    ) as pipeline:
        captured = pipeline.capture(
            CaptureRequest(source_type="note", origin="empty.md", content="A real source")
        )
        result = pipeline.process_pending()[0]
        envelope = pipeline.store.get_envelope(result.envelope_id or "")

        assert result.status == "review_pending"
        assert envelope is not None
        assert {signal.code for signal in envelope.review_signals} == {
            "empty_semantic_extraction"
        }
        assert pipeline.store.pending_reviews()[0]["items"] == []
        assert captured.source_record_id == envelope.source_record_id
        assert kg.calls == []


def test_deterministic_review_rechecks_concept_evidence_and_exact_range(
    tmp_path: Path,
) -> None:
    with UnifiedIngestionPipeline(
        config(tmp_path), extractor=MissingConceptEvidenceExtractor()
    ) as pipeline:
        pipeline.capture(
            CaptureRequest(
                source_type="note",
                origin="evidence.md",
                content="Duration measures rate sensitivity.",
            )
        )
        result = pipeline.process_pending()[0]
        review = pipeline.store.pending_reviews()[0]
        signal_codes = {
            signal["code"] for signal in review["envelope"]["review_signals"]
        }
        item_reasons = {
            item["proposal_type"]: set(item["reasons"]) for item in review["items"]
        }

        assert result.status == "review_pending"
        assert signal_codes == {"missing_evidence", "evidence_quote_mismatch"}
        assert item_reasons["concept"] == {"missing_evidence"}
        assert item_reasons["claim"] == {"evidence_quote_mismatch"}


def test_proposals_can_be_reviewed_individually_and_edits_are_retained(
    tmp_path: Path,
) -> None:
    extractor = FixtureExtractor(alias=True)
    kg = RecordingConsumer("kg")
    with UnifiedIngestionPipeline(
        config(tmp_path), extractor=extractor, consumers=[kg]
    ) as pipeline:
        pipeline.capture(
            CaptureRequest(
                source_type="note",
                origin="per-proposal.md",
                content="Duration measures rate sensitivity.",
            )
        )
        pending = pipeline.process_pending()[0]
        envelope = pipeline.store.get_envelope(pending.envelope_id or "")
        assert envelope is not None
        concept = envelope.semantic.concepts[0]
        claim = envelope.semantic.claims[0]

        partial = pipeline.resolve_proposal_reviews(
            envelope.envelope_id,
            decisions=[
                ProposalReviewDecision(
                    proposal_id=concept.proposal_id,
                    action="reject",
                    note="Alias is not safe to merge.",
                )
            ],
            resolver="pytest",
        )
        assert partial.status == "review_pending"
        assert kg.calls == []

        edited_claim = claim.model_dump(mode="json")
        edited_claim["text"] = "Duration describes sensitivity to rate changes."
        complete = pipeline.resolve_proposal_reviews(
            envelope.envelope_id,
            decisions=[
                ProposalReviewDecision(
                    proposal_id=claim.proposal_id,
                    action="edit",
                    edited_proposal=edited_claim,
                    note="Clarified wording.",
                )
            ],
            resolver="pytest",
        )
        stored = pipeline.store.get_envelope(envelope.envelope_id)
        rows = {
            row["proposal_id"]: row
            for row in pipeline.store.rows("review_items")
        }

        assert complete.status == "processed"
        assert len(kg.calls) == 1
        assert stored is not None
        assert stored.review_status == "approved"
        assert stored.semantic.concepts[0].status == "rejected"
        assert stored.semantic.claims[0].status == "current"
        assert stored.semantic.claims[0].text == edited_claim["text"]
        assert rows[concept.proposal_id]["decision"] == "reject"
        assert rows[claim.proposal_id]["decision"] == "edit"
        assert (
            rows[claim.proposal_id]["original_proposal_json"]
            != rows[claim.proposal_id]["final_proposal_json"]
        )


def test_editing_a_relation_proposal_preserves_hierarchical_and_evidence(
    tmp_path: Path,
) -> None:
    """The cockpit sends edited_proposal as a full-model spread: the read-only
    fields the reviewer never sees (hierarchical, evidence) are carried through
    unchanged from the original wire payload, not reconstructed. This is the
    exact shape the review UI must submit -- if a client ever omitted one of
    these, `hierarchical` would silently default to False and defeat cycle
    detection in kg_consumer with no error raised anywhere (see models.py).
    """
    extractor = RelationFixtureExtractor()
    with UnifiedIngestionPipeline(config(tmp_path), extractor=extractor) as pipeline:
        pipeline.capture(
            CaptureRequest(
                source_type="note",
                origin="hierarchy.md",
                content="Duration is a prerequisite of Convexity.",
            )
        )
        pending = pipeline.process_pending()[0]
        envelope = pipeline.store.get_envelope(pending.envelope_id or "")
        assert envelope is not None
        relation = envelope.semantic.relations[0]
        assert relation.hierarchical is True

        # The full wire payload a reviewer would receive, with only the
        # editable content field (predicate) changed -- exactly what
        # KnowledgeProposalReview.tsx's buildPayload() for `edit` sends.
        edited_relation = relation.model_dump(mode="json")
        edited_relation["predicate"] = "strictly precedes"

        pipeline.resolve_proposal_reviews(
            envelope.envelope_id,
            decisions=[
                ProposalReviewDecision(
                    proposal_id=relation.proposal_id,
                    action="edit",
                    edited_proposal=edited_relation,
                    note="Clarified predicate wording.",
                )
            ],
            resolver="pytest",
        )

        stored = pipeline.store.get_envelope(envelope.envelope_id)
        assert stored is not None
        stored_relation = stored.semantic.relations[0]
        assert stored_relation.predicate == "strictly precedes"
        assert stored_relation.status == "approved"
        # Neither read-only field was reconstructed from a default; both
        # survived the edit exactly as they were before it.
        assert stored_relation.hierarchical is True
        assert [item.model_dump(mode="json") for item in stored_relation.evidence] == [
            item.model_dump(mode="json") for item in relation.evidence
        ]


def test_failed_dispatch_retries_without_duplicate_success(tmp_path: Path) -> None:
    extractor = FixtureExtractor()
    kg = RecordingConsumer("kg")
    vector = RecordingConsumer("vector", failures=1)
    with UnifiedIngestionPipeline(config(tmp_path), extractor=extractor, consumers=[kg, vector]) as pipeline:
        captured = pipeline.capture(
            CaptureRequest(source_type="article", origin="https://example.com/a", content="A claim")
        )
        first = pipeline.process_pending()[0]
        second = pipeline.process_source(captured.source_record_id)[0]
        third = pipeline.process_source(captured.source_record_id)[0]

        dispatches = {row["target"]: row for row in pipeline.store.rows("dispatches")}
        assert first.dispatched_targets == ["kg"]
        assert second.dispatched_targets == ["vector"]
        assert third.dispatched_targets == []
        assert dispatches["kg"]["status"] == "done"
        assert dispatches["kg"]["attempts"] == 1
        assert dispatches["vector"]["status"] == "done"
        assert dispatches["vector"]["attempts"] == 2
        assert len(kg.calls) == 1
        assert len(vector.calls) == 2


def test_successful_redispatch_does_not_duplicate_kg_writes(tmp_path: Path) -> None:
    """T10: re-dispatching an already-`done` envelope must be a true no-op.

    Exercises the real `Dispatcher` (status-skip on `dispatches`) driving the
    real `KGConsumer`, backed by a store with no dedup of its own
    (`RecordingKGStore`). If the Dispatcher's skip logic ever regressed and
    called `consume()` a second time, the claim/edge counts below would
    double instead of staying flat.
    """
    extractor = FixtureExtractor()
    kg_store = RecordingKGStore()
    kg = KGConsumer(kg_store)
    with UnifiedIngestionPipeline(config(tmp_path), extractor=extractor, consumers=[kg]) as pipeline:
        captured = pipeline.capture(
            CaptureRequest(source_type="article", origin="https://example.com/a", content="A claim")
        )
        first = pipeline.process_pending()[0]
        second = pipeline.process_source(captured.source_record_id)[0]
        third = pipeline.process_source(captured.source_record_id)[0]

        assert first.dispatched_targets == ["kg"]
        assert second.dispatched_targets == []
        assert third.dispatched_targets == []
        assert second.status == "already_processed"
        assert third.status == "already_processed"

        dispatch = list(pipeline.store.rows("dispatches"))[0]
        assert dispatch["status"] == "done"
        assert dispatch["attempts"] == 1

        # The real assertion: three dispatch attempts, one actual write.
        assert len(kg_store.claims) == 1
        assert kg_store.claims[0].subject_id == "node:Duration"


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


def test_photo_derived_highlight_is_always_reviewed(tmp_path: Path) -> None:
    page_scanner_consumer = RecordingConsumer("kg")
    with UnifiedIngestionPipeline(
        config(tmp_path / "scanner"),
        extractor=FixtureExtractor(),
        consumers=[page_scanner_consumer],
    ) as pipeline:
        pipeline.capture(
            CaptureRequest(
                source_type="obsidian_note",
                origin="scan.md",
                content="Duration",
                metadata={"origin_kind": "page_scanner"},
            )
        )
        scanner_outcome = pipeline.process_pending()[0]
        scanner_envelope = pipeline.store.get_envelope(scanner_outcome.envelope_id or "")

    typed_consumer = RecordingConsumer("kg")
    with UnifiedIngestionPipeline(
        config(tmp_path / "typed"),
        extractor=FixtureExtractor(),
        consumers=[typed_consumer],
    ) as pipeline:
        pipeline.capture(
            CaptureRequest(
                source_type="obsidian_note",
                origin="typed.md",
                content="Duration",
                metadata={"origin_kind": "obsidian_note"},
            )
        )
        typed_outcome = pipeline.process_pending()[0]

    assert scanner_outcome.status == "review_pending"
    assert scanner_envelope is not None
    assert "source_is_page_scanner" in {
        signal.code for signal in scanner_envelope.review_signals
    }
    assert page_scanner_consumer.calls == []
    assert typed_outcome.status == "processed"
    assert len(typed_consumer.calls) == 1


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
            "parses",
            "parse_failures",
            "highlights",
            "envelopes",
            "review_queue",
            "review_items",
            "dispatches",
            "quarantine",
        }


def test_envelope_is_recoverable_as_an_immutable_creation_snapshot(
    tmp_path: Path,
) -> None:
    cfg = config(tmp_path)
    with UnifiedIngestionPipeline(
        cfg,
        extractor=FixtureExtractor(alias=True),
    ) as pipeline:
        pipeline.capture(
            CaptureRequest(source_type="note", origin="snapshot.md", content="Duration")
        )
        pending = pipeline.process_pending()[0]
        artifact = cfg.envelope_root / f"{pending.envelope_id}.json"
        creation_snapshot = artifact.read_text(encoding="utf-8")
        pipeline.resolve_review(
            pending.envelope_id or "",
            approved=True,
            resolver="pytest",
        )
        current = pipeline.store.get_envelope(pending.envelope_id or "")

    payload = IngestionEnvelope.model_validate_json(creation_snapshot)
    assert payload.review_status == "pending"
    assert current is not None
    assert current.review_status == "approved"
    assert artifact.read_text(encoding="utf-8") == creation_snapshot
    assert os.stat(artifact).st_mode & 0o222 == 0
    assert not (cfg.database_root / "handoff").exists()


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


def test_extraction_failure_marks_item_failed_and_self_retries(tmp_path: Path) -> None:
    extractor = FlakyExtractor(fail_times=1)
    with UnifiedIngestionPipeline(config(tmp_path), extractor=extractor) as pipeline:
        captured = pipeline.capture(
            CaptureRequest(source_type="note", origin="flaky.md", content="Duration risk note")
        )

        first = pipeline.process_pending()[0]
        assert first.status == "extraction_failed"
        assert first.envelope_id is None
        assert len(list(pipeline.store.rows("envelopes"))) == 0

        second = pipeline.process_pending()[0]
        assert second.source_record_id == captured.source_record_id
        assert second.status in {"processed", "review_pending"}
        assert extractor.calls == 2


def test_one_extraction_failure_does_not_abort_the_rest_of_the_batch(tmp_path: Path) -> None:
    extractor = FlakyExtractor()
    with UnifiedIngestionPipeline(config(tmp_path), extractor=extractor) as pipeline:
        bad = pipeline.capture(
            CaptureRequest(source_type="note", origin="bad.md", content="Bad document")
        )
        good = pipeline.capture(
            CaptureRequest(source_type="note", origin="good.md", content="Good document")
        )
        extractor.fail_for = {bad.source_record_id}

        results = {result.source_record_id: result for result in pipeline.process_pending()}

        assert results[bad.source_record_id].status == "extraction_failed"
        assert results[good.source_record_id].status in {"processed", "review_pending"}


def test_raw_publication_is_atomic_and_never_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = tmp_path / "raw" / "published.raw"
    UnifiedIngestionPipeline._write_immutable(published, b"complete")

    with pytest.raises(RuntimeError, match="Immutable artifact collision"):
        UnifiedIngestionPipeline._write_immutable(published, b"different")
    assert published.read_bytes() == b"complete"

    failed = tmp_path / "raw" / "failed.raw"

    def fail_publish(_source: Path, _destination: Path) -> None:
        raise OSError("simulated publication failure")

    monkeypatch.setattr(os, "link", fail_publish)
    with pytest.raises(OSError, match="simulated publication failure"):
        UnifiedIngestionPipeline._write_immutable(failed, b"never partial")

    assert not failed.exists()
    assert not list(failed.parent.glob(f".{failed.name}.*.tmp"))


# --------------------------------------------------------------------------
# T33: the highlight is the atomic unit
# --------------------------------------------------------------------------

TWO_HIGHLIGHT_NOTE = """# Photosynthesis

Photosynthesis converts light energy into chemical energy in plants. \
Chlorophyll absorbs light energy. Chloroplasts contain chlorophyll. During \
photosynthesis, plants use carbon dioxide and water to produce glucose and \
oxygen. Glucose stores chemical energy. Plants release oxygen into the \
atmosphere.

# Respiration

Respiration releases the energy stored in glucose. Mitochondria carry out \
respiration in the cell. The process consumes oxygen and produces carbon \
dioxide. Aerobic respiration yields far more energy than anaerobic \
respiration does in most organisms studied.
"""


class PerHighlightExtractor:
    """Good evidence for every highlight except the ones naming a bad word."""

    def __init__(self, *, poison: str | None = None) -> None:
        self.poison = poison
        self.seen: list[str] = []

    def extract(self, *, source_record_id, normalized_content, metadata) -> ExtractionResult:
        del metadata
        self.seen.append(normalized_content)
        quote = (
            "a quote this highlight does not contain"
            if self.poison and self.poison in normalized_content
            else normalized_content.strip()
        )
        return ExtractionResult(
            semantic=SemanticExtraction(
                concepts=[
                    ConceptProposal(
                        proposal_id=f"concept-{source_record_id}-0",
                        label="Energy",
                        confidence=0.95,
                        source_record_id=source_record_id,
                        evidence=[
                            EvidenceRef(
                                source_record_id=source_record_id,
                                quote=quote,
                                normalized_char_start=0,
                                normalized_char_end=len(quote),
                            )
                        ],
                    )
                ],
            ),
            confidence=0.95,
        )


class CountingBatchExtractor(PerHighlightExtractor):
    """Batches for real, so the pipeline takes the batched path."""

    def __init__(self, *, poison: str | None = None, fail_batches: int = 0) -> None:
        super().__init__(poison=poison)
        self.batch_calls: list[int] = []
        self.fail_batches = fail_batches

    def extract_batch(self, items) -> dict:
        self.batch_calls.append(len(items))
        if self.fail_batches > 0:
            self.fail_batches -= 1
            raise ExtractionError("gateway unavailable for this batch")
        return {
            item.batch_item_id: self.extract(
                source_record_id=item.source_record_id,
                normalized_content=item.highlight_text,
                metadata=item.metadata,
            )
            for item in items
        }


def capture_note(pipeline: UnifiedIngestionPipeline, origin: str = "note.md", content: str = TWO_HIGHLIGHT_NOTE):
    return pipeline.capture(
        CaptureRequest(source_type="note", origin=origin, content=content)
    )


def test_a_document_becomes_one_envelope_per_highlight(tmp_path: Path) -> None:
    extractor = PerHighlightExtractor()
    with UnifiedIngestionPipeline(config(tmp_path), extractor=extractor) as pipeline:
        captured = capture_note(pipeline)
        outcomes = pipeline.process_pending()

        assert len(outcomes) == 2
        assert [outcome.highlight_index for outcome in outcomes] == [0, 1]
        assert all(o.source_record_id == captured.source_record_id for o in outcomes)
        # Distinct envelope ids: sharing one id would make save_envelope's
        # INSERT OR IGNORE silently drop every sibling but the first.
        envelope_ids = {outcome.envelope_id for outcome in outcomes}
        assert len(envelope_ids) == 2
        assert len(list(pipeline.store.rows("envelopes"))) == 2
        assert len(list(pipeline.store.rows("highlights"))) == 2


def test_parse_failure_is_atomic_retriable_and_does_not_stop_other_documents(
    tmp_path: Path,
) -> None:
    class SelectiveSegmenter:
        def __init__(self) -> None:
            self.fail = True
            self.heading = HeadingTopicSegmenter()

        def boundary_decision(self, block):
            if self.fail and "FAIL_SEGMENT" in block:
                raise RuntimeError("forced segmentation failure")
            return self.heading.boundary_decision(block)

    segmenter = SelectiveSegmenter()
    bad_note = TWO_HIGHLIGHT_NOTE.replace(
        "Photosynthesis converts", "FAIL_SEGMENT Photosynthesis converts"
    )
    with UnifiedIngestionPipeline(
        config(tmp_path),
        extractor=PerHighlightExtractor(),
        segmenter=segmenter,
    ) as pipeline:
        failed = capture_note(pipeline, "bad.md", bad_note)
        good = capture_note(pipeline, "good.md")

        first_run = pipeline.process_pending()

        assert [outcome.status for outcome in first_run].count("parse_failed") == 1
        assert [outcome.status for outcome in first_run].count("processed") == 2
        assert pipeline.store.highlight_count(failed.source_record_id) is None
        assert pipeline.store.get_highlights(failed.source_record_id) == []
        assert pipeline.store.highlight_count(good.source_record_id) == 2
        failures = pipeline.store.parse_failures(failed.source_record_id)
        assert len(failures) == 1
        assert failures[0]["failure_type"] == "segmenter_exception"
        assert failures[0]["resolved_at"] is None

        segmenter.fail = False
        second_run = pipeline.process_pending()

        assert [outcome.status for outcome in second_run] == [
            "processed",
            "processed",
        ]
        assert pipeline.store.highlight_count(failed.source_record_id) == 2
        assert pipeline.store.parse_failures(failed.source_record_id)[0][
            "resolved_at"
        ] is not None


def test_user_selection_bypasses_document_segmentation_and_keeps_parent_pointer(
    tmp_path: Path,
) -> None:
    class MustNotRun:
        def boundary_decision(self, block):
            raise AssertionError("user selection reached the document segmenter")

    context = "Bond duration measures interest-rate sensitivity."
    with UnifiedIngestionPipeline(
        config(tmp_path),
        extractor=PerHighlightExtractor(),
        segmenter=MustNotRun(),
    ) as pipeline:
        captured = pipeline.capture(
            CaptureRequest(
                source_type="highlight",
                origin="capture://duration",
                content="duration",
                boundary_origin="user_selection",
                user_selection=UserSelection(
                    context_text=context,
                    parent_source_ref="obsidian://bonds",
                    parent_start_char=5,
                    parent_end_char=13,
                    containing_sentence=context,
                ),
            )
        )

        outcomes = pipeline.process_pending()
        envelopes = pipeline.store.get_envelopes_for_source(
            captured.source_record_id,
            pipeline.config.extraction_version,
        )

        assert [outcome.status for outcome in outcomes] == ["processed"]
        assert len(envelopes) == 1
        envelope = envelopes[0]
        assert envelope.highlight_text == "duration"
        assert envelope.highlight_context_text == context
        assert envelope.highlight_boundary_origin == "user_selection"
        assert envelope.highlight_parent_source_ref == "obsidian://bonds"
        assert envelope.highlight_parent_start_char == 5
        assert envelope.highlight_parent_end_char == 13


def test_one_bad_highlight_does_not_block_its_siblings(tmp_path: Path) -> None:
    """The whole point of T33 — and it needs no Dispatcher or policy change.

    Before this, one unverifiable evidence quote anywhere in a note held the
    entire note out of Neo4j, Chroma, and SQLite until a human resolved it.
    """
    extractor = PerHighlightExtractor(poison="Respiration")
    kg = RecordingConsumer("kg")
    with UnifiedIngestionPipeline(
        config(tmp_path), extractor=extractor, consumers=[kg]
    ) as pipeline:
        capture_note(pipeline)
        outcomes = {o.highlight_index: o for o in pipeline.process_pending()}

        assert outcomes[0].status == "processed"
        assert outcomes[0].dispatched_targets == ["kg"]
        assert outcomes[1].status == "review_pending"
        assert outcomes[1].dispatched_targets == []
        # The clean highlight reached the consumer; the flagged one did not.
        assert len(kg.calls) == 1
        assert kg.calls[0].highlight_index == 0
        assert len(pipeline.store.pending_reviews()) == 1


def test_sibling_highlights_never_share_a_proposal_id(tmp_path: Path) -> None:
    # The extractor mints the same proposal id for every highlight it sees.
    # That id becomes a global key downstream (KG edge/claim ids, the content
    # store's claim primary key), so an unscoped collision would merge two
    # highlights' beliefs into one row.
    extractor = PerHighlightExtractor()
    with UnifiedIngestionPipeline(config(tmp_path), extractor=extractor) as pipeline:
        captured = capture_note(pipeline)
        pipeline.process_pending()

        envelopes = pipeline.store.get_envelopes_for_source(
            captured.source_record_id, pipeline.config.extraction_version
        )
        proposal_ids = [e.semantic.concepts[0].proposal_id for e in envelopes]
        assert len(proposal_ids) == 2
        assert len(set(proposal_ids)) == 2


def test_parse_output_is_stored_once_and_never_recomputed(tmp_path: Path) -> None:
    # The segmenter is model-backed and its boundaries are not reproducible, so
    # re-splitting a document would renumber highlights and orphan every
    # projection keyed on the old indices.
    class CountingSegmenter(HeadingTopicSegmenter):
        def __init__(self) -> None:
            self.calls = 0

        def second_topic(self, block: str) -> str:
            self.calls += 1
            return super().second_topic(block)

    segmenter = CountingSegmenter()
    with UnifiedIngestionPipeline(
        config(tmp_path), extractor=PerHighlightExtractor(), segmenter=segmenter
    ) as pipeline:
        captured = capture_note(pipeline)
        pipeline.process_pending()
        after_first = segmenter.calls
        # Guard the guard: if the fixture ever fell under the semantic floor
        # the segmenter would never be called and this test would pass vacuously.
        assert after_first > 0

        pipeline.process_pending()
        pipeline.process_source(captured.source_record_id)

        assert segmenter.calls == after_first
        assert len(list(pipeline.store.rows("highlights"))) == 2
        assert pipeline.store.highlight_count(captured.source_record_id) == 2


def test_highlights_carry_their_real_text_and_surrounding_context(tmp_path: Path) -> None:
    with UnifiedIngestionPipeline(
        config(tmp_path), extractor=PerHighlightExtractor()
    ) as pipeline:
        captured = capture_note(pipeline)
        pipeline.process_pending()

        envelopes = pipeline.store.get_envelopes_for_source(
            captured.source_record_id, pipeline.config.extraction_version
        )
        first, second = envelopes
        assert "Photosynthesis converts light energy" in first.highlight_text
        assert "Respiration releases the energy" in second.highlight_text
        # Real context on both sides, not a stub and not a copy of the document.
        assert first.highlight_context_text is not None
        assert "Respiration releases the energy" in first.highlight_context_text
        assert second.highlight_context_text is not None
        assert "Plants release oxygen" in second.highlight_context_text
        assert first.highlight_end_char <= second.highlight_start_char


def test_a_batching_extractor_covers_several_documents_in_one_call(tmp_path: Path) -> None:
    extractor = CountingBatchExtractor()
    cfg = IngestionConfig(
        database_root=tmp_path / "Database",
        extraction_batch_size=3,
        segmentation=SegmentationConfig(mode="deterministic"),
    )
    with UnifiedIngestionPipeline(cfg, extractor=extractor) as pipeline:
        capture_note(pipeline, "a.md")
        capture_note(pipeline, "b.md", TWO_HIGHLIGHT_NOTE.replace("energy", "power"))
        outcomes = pipeline.process_pending()

        # 4 highlights across 2 documents, batch size 3 -> ceil(4/3) = 2 calls,
        # not 4. A batch is allowed to span documents.
        assert len(outcomes) == 4
        assert extractor.batch_calls == [3, 1]


def test_a_failed_batch_leaves_exactly_its_own_items_pending(tmp_path: Path) -> None:
    extractor = CountingBatchExtractor(fail_batches=1)
    cfg = IngestionConfig(
        database_root=tmp_path / "Database",
        extraction_batch_size=2,
        segmentation=SegmentationConfig(mode="deterministic"),
    )
    with UnifiedIngestionPipeline(cfg, extractor=extractor) as pipeline:
        capture_note(pipeline, "a.md")
        capture_note(pipeline, "b.md", TWO_HIGHLIGHT_NOTE.replace("energy", "power"))
        first_run = pipeline.process_pending()

        # The first batch of 2 failed; the second was unaffected.
        statuses = [outcome.status for outcome in first_run]
        assert statuses.count("extraction_failed") == 2
        assert statuses.count("processed") == 2
        assert len(list(pipeline.store.rows("envelopes"))) == 2

        # The failed items are still pending, and a later run picks them up
        # without re-parsing or re-extracting the ones that already succeeded.
        second_run = pipeline.process_pending()
        assert len(second_run) == 2
        assert all(outcome.status == "processed" for outcome in second_run)
        assert len(list(pipeline.store.rows("envelopes"))) == 4


def test_a_non_batching_extractor_keeps_per_highlight_failure_isolation(
    tmp_path: Path,
) -> None:
    # Batching only pays off when the extractor really batches. An extractor
    # called once per highlight anyway is given batches of one, so one bad
    # highlight cannot fail its neighbours for no saving.
    class OneBadHighlightExtractor(PerHighlightExtractor):
        def extract(self, *, source_record_id, normalized_content, metadata):
            if "Respiration" in normalized_content:
                raise ExtractionError("gateway unavailable")
            return super().extract(
                source_record_id=source_record_id,
                normalized_content=normalized_content,
                metadata=metadata,
            )

    with UnifiedIngestionPipeline(
        config(tmp_path), extractor=OneBadHighlightExtractor()
    ) as pipeline:
        capture_note(pipeline)
        outcomes = {o.highlight_index: o for o in pipeline.process_pending()}

        assert outcomes[0].status == "processed"
        assert outcomes[1].status == "extraction_failed"


def test_sibling_highlights_reach_the_vector_store_with_distinct_chunk_ids(
    tmp_path: Path,
) -> None:
    # Siblings share one `normalized_content_hash`, so the old document-hash
    # chunk id gave every highlight the same id and each write silently
    # overwrote the last.
    from ingestion_tests.test_vector_consumer import FakeEmbeddingClient, FakeVectorStore

    from gateway.ingestion.consumers.vector_consumer import VectorConsumer

    store = FakeVectorStore()
    with UnifiedIngestionPipeline(
        config(tmp_path),
        extractor=PerHighlightExtractor(),
        consumers=[VectorConsumer(store, embedding_client=FakeEmbeddingClient())],
    ) as pipeline:
        capture_note(pipeline)
        pipeline.process_pending()

        written_ids = [ids[0] for _, ids, _, _, _ in store.upserts]
        written_texts = [texts[0] for _, _, texts, _, _ in store.upserts]
        assert len(written_ids) == 2
        assert len(set(written_ids)) == 2
        # Each highlight is embedded as itself, not as the whole document.
        assert "Photosynthesis converts" in written_texts[0]
        assert "Respiration releases" in written_texts[1]


def test_a_long_highlight_is_stored_once_but_vectorized_in_child_chunks(
    tmp_path: Path,
) -> None:
    from ingestion_tests.test_vector_consumer import FakeEmbeddingClient, FakeVectorStore

    from gateway.ingestion.consumers.vector_consumer import VectorConsumer

    long_note = "# Note\n\n" + " ".join(f"word{n}" for n in range(400)) + "."
    store = FakeVectorStore()
    with UnifiedIngestionPipeline(
        config(tmp_path),
        extractor=PerHighlightExtractor(),
        consumers=[VectorConsumer(store, embedding_client=FakeEmbeddingClient())],
    ) as pipeline:
        capture_note(pipeline, "long.md", long_note)
        pipeline.process_pending()

        collection, ids, texts, metadatas, embeddings = store.upserts[0]
        assert len(texts) == 4
        assert all(len(text.split()) <= 150 for text in texts)
        assert all(metadata["chunk_total"] == 4 for metadata in metadatas)
        assert len(list(pipeline.store.rows("highlights"))) == 1


def test_a_document_with_nothing_parseable_is_reported_and_not_reparsed(
    tmp_path: Path,
) -> None:
    with UnifiedIngestionPipeline(config(tmp_path)) as pipeline:
        pipeline.capture(
            CaptureRequest(source_type="note", origin="blank.md", content="   \n\n  \n")
        )
        first = pipeline.process_pending()

        assert [outcome.status for outcome in first] == ["empty_parse"]
        # Recorded as parsed, so it does not come back every run.
        assert pipeline.store.highlight_count(first[0].source_record_id) == 0
        assert pipeline.process_pending() == []


def test_typed_highlight_with_a_cleanup_suggestion_is_reviewed(tmp_path: Path) -> None:
    """Both gates: a typed highlight auto-ingests only with no suggestion."""

    class OneSuggestion:
        def suggestions(self, highlight_text: str) -> tuple[str, ...]:
            del highlight_text
            return ("expand 'e.g.'",)

    gated_consumer = RecordingConsumer("kg")
    with UnifiedIngestionPipeline(
        config(tmp_path / "gated"),
        extractor=FixtureExtractor(),
        consumers=[gated_consumer],
        highlight_cleanup=OneSuggestion(),
    ) as pipeline:
        pipeline.capture(
            CaptureRequest(
                source_type="obsidian_note",
                origin="typed.md",
                content="Duration",
                metadata={"origin_kind": "obsidian_note"},
            )
        )
        gated_outcome = pipeline.process_pending()[0]
        gated_envelope = pipeline.store.get_envelope(gated_outcome.envelope_id or "")

    shipped_consumer = RecordingConsumer("kg")
    with UnifiedIngestionPipeline(
        config(tmp_path / "shipped"),
        extractor=FixtureExtractor(),
        consumers=[shipped_consumer],
    ) as pipeline:
        pipeline.capture(
            CaptureRequest(
                source_type="obsidian_note",
                origin="typed.md",
                content="Duration",
                metadata={"origin_kind": "obsidian_note"},
            )
        )
        shipped_outcome = pipeline.process_pending()[0]

    assert gated_outcome.status == "review_pending"
    assert gated_envelope is not None
    assert "cleanup_suggestion_pending" in {
        signal.code for signal in gated_envelope.review_signals
    }
    assert gated_consumer.calls == []
    # The stub T60 ships returns nothing, so landed behaviour is unchanged.
    assert shipped_outcome.status == "processed"
    assert len(shipped_consumer.calls) == 1
