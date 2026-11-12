"""Tests for dispatching envelopes to the SQLite content projection."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from ingestion.config import IngestionConfig
from ingestion.consumers.content_consumer import ContentConsumer
from ingestion.content_store import CONTENT_TABLES, ContentStore
from ingestion.dispatch import Dispatcher
from ingestion.ids import highlight_id_for_highlight
from ingestion.models import (
    AccessPolicy,
    EvidenceRef,
    IngestionEnvelope,
    RelationProposal,
    SemanticExtraction,
)
from ingestion.routing import DEFAULT_ALLOWED_CONSUMERS


class DispatchLedger:
    """Minimal in-memory implementation of the dispatch ledger interface."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str], dict[str, Any]] = {}

    def dispatch_status(
        self, envelope_id: str, target: str, extraction_version: str
    ) -> dict[str, Any] | None:
        return self.records.get((envelope_id, target, extraction_version))

    def record_dispatch(
        self,
        *,
        envelope_id: str,
        target: str,
        extraction_version: str,
        status: str,
        artifact_ref: str | None = None,
        error: str | None = None,
    ) -> None:
        self.records[(envelope_id, target, extraction_version)] = {
            "status": status,
            "artifact_ref": artifact_ref,
            "error": error,
        }


def envelope(
    *,
    source_record_id: str = "record-1",
    supersedes_record_id: str | None = None,
    supersedes_highlight_count: int | None = None,
    highlight_index: int = 0,
    highlight_text: str = "Duration measures rate sensitivity.",
    evidence: str = "duration measures rate sensitivity",
) -> IngestionEnvelope:
    relation = RelationProposal(
        proposal_id=f"relation-{source_record_id}-{highlight_index}",
        subject="Duration",
        predicate="MEASURES",
        object="Rate sensitivity",
        model_confidence=0.9,
        status="approved",
        source_record_id=source_record_id,
        domain="finance",
        evidence=[
            EvidenceRef(source_record_id=source_record_id, quote=evidence),
        ],
    )
    return IngestionEnvelope(
        envelope_id=f"envelope-{source_record_id}-{highlight_index}",
        source_record_id=source_record_id,
        canonical_record_id="canonical-1",
        source_type="obsidian_note",
        origin="vault/note.md",
        normalized_origin="vault/note.md",
        captured_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        observed_at=None,
        raw_content_ref=f"bronze/{source_record_id}.md",
        raw_content_hash=f"raw-{source_record_id}",
        normalized_content_hash=f"normalized-{source_record_id}",
        highlight_index=highlight_index,
        highlight_text=highlight_text,
        highlight_context_text="Preceding sentence. […] Following sentence.",
        highlight_start_char=0,
        highlight_end_char=len(highlight_text),
        version=2 if supersedes_record_id else 1,
        supersedes_record_id=supersedes_record_id,
        supersedes_highlight_count=supersedes_highlight_count,
        access_policy=AccessPolicy(),
        extraction_version="semantic_extraction_v1",
        semantic=SemanticExtraction(relations=[relation], field_tags=["finance"]),
        model_confidence=0.9,
        review_status="approved",
    )


@pytest.fixture
def content_store(tmp_path: Path) -> ContentStore:
    store = ContentStore(tmp_path / "content.db")
    try:
        yield store
    finally:
        store.close()


def test_consume_projects_content_and_returns_artifact_ref(
    content_store: ContentStore,
) -> None:
    item = envelope()

    artifact_ref = ContentConsumer(content_store).consume(item)

    assert artifact_ref == f"sqlite:{item.envelope_id}"
    assert content_store.table_names() == set(CONTENT_TABLES)
    assert content_store.count("source") == 1
    assert content_store.count("acquisition") == 1
    assert content_store.count("highlight") == 1
    assert content_store.count("transformation") == 1
    assert content_store.count("claim") == 1
    assert content_store.count("tag") == 1
    assert content_store.count("comment") == 0


def test_dispatcher_records_done_after_successful_projection(
    content_store: ContentStore,
) -> None:
    item = envelope()
    ledger = DispatchLedger()

    results = Dispatcher(ledger, [ContentConsumer(content_store)]).dispatch(item)

    assert len(results) == 1
    assert results[0].status == "done"
    assert results[0].artifact_ref == f"sqlite:{item.envelope_id}"
    assert content_store.count("highlight") == 1


def test_dispatcher_records_failed_when_projection_raises() -> None:
    class FailingStore:
        def project_envelope(self, _envelope: IngestionEnvelope) -> str:
            raise RuntimeError("content database unavailable")

    ledger = DispatchLedger()
    consumer = ContentConsumer(FailingStore())

    results = Dispatcher(ledger, [consumer]).dispatch(envelope())

    assert len(results) == 1
    assert results[0].status == "failed"
    assert results[0].status != "done"
    assert results[0].error == "content database unavailable"
    assert next(iter(ledger.records.values()))["status"] == "failed"


def test_redispatch_of_done_target_is_skipped(
    content_store: ContentStore,
) -> None:
    item = envelope()
    ledger = DispatchLedger()
    dispatcher = Dispatcher(ledger, [ContentConsumer(content_store)])

    first = dispatcher.dispatch(item)
    second = dispatcher.dispatch(item)

    assert first[0].status == "done"
    assert second[0].status == "skipped"
    assert second[0].artifact_ref == f"sqlite:{item.envelope_id}"
    assert content_store.count("highlight") == 1


def test_supersede_replaces_predecessor_through_dispatch(
    content_store: ContentStore,
) -> None:
    ledger = DispatchLedger()
    dispatcher = Dispatcher(ledger, [ContentConsumer(content_store)])

    first = envelope()
    second = envelope(
        source_record_id="record-2",
        supersedes_record_id=first.source_record_id,
        evidence="duration measures interest rate risk",
    )
    assert dispatcher.dispatch(first)[0].status == "done"
    assert dispatcher.dispatch(second)[0].status == "done"

    highlights = {
        row["highlight_id"] for row in content_store.rows("highlight")
    }
    assert highlight_id_for_highlight(first.source_record_id, 0) not in highlights
    assert highlight_id_for_highlight(second.source_record_id, 0) in highlights
    claims = list(content_store.rows("claim"))
    assert len(claims) == 1
    assert claims[0]["evidence_text"] == "duration measures interest rate risk"


def test_sqlite_target_is_permitted_by_default_routing() -> None:
    assert ContentConsumer.target == "sqlite"
    assert ContentConsumer.target in DEFAULT_ALLOWED_CONSUMERS


def test_content_db_path_is_separate_from_ledger(tmp_path: Path) -> None:
    config = IngestionConfig(database_root=tmp_path / "Database")

    assert config.content_db_path == config.database_root / "sqlite" / "content.db"
    assert config.content_db_path != config.ledger_path
