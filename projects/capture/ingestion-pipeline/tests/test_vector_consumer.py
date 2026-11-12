from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ingestion.config import EmbeddingChunkConfig
from ingestion.consumers.kg_consumer import highlight_id_for_highlight
from ingestion.consumers.vector_consumer import VectorConsumer
from ingestion.models import AccessPolicy, IngestionEnvelope, SemanticExtraction
from ingestion.normalization import normalize_source
from ingestion.vector.vector_store import EMBEDDING_DIMENSION


class FakeEmbeddingClient:
    def __init__(self, *, provider: str = "ollama", dimension: int = 768) -> None:
        self.provider = provider
        self.dimension = dimension
        self.calls: list[tuple[str, str, str | None]] = []

    def embed(self, text, task_type="retrieval_document", provider=None):
        self.calls.append((text, task_type, provider))
        return {
            "provider": self.provider,
            "model": (
                "nomic-embed-text" if self.provider == "ollama" else "gemini-embedding-001"
            ),
            "dim": self.dimension,
            "embedding": [0.0] * self.dimension,
        }


class FakeVectorStore:
    def __init__(self, *, fail_upsert: bool = False) -> None:
        self.fail_upsert = fail_upsert
        self.writable_checks: list[str] = []
        self.purges: list[tuple[str, str]] = []
        self.upserts: list[tuple] = []

    def ensure_writable(self, collection: str) -> None:
        self.writable_checks.append(collection)

    def delete_by_source_id(self, collection: str, source_id: str) -> None:
        self.purges.append((collection, source_id))

    def upsert_batch(self, collection, ids, texts, metadatas, embeddings) -> None:
        if self.fail_upsert:
            raise RuntimeError("Chroma write failed")
        self.upserts.append((collection, ids, texts, metadatas, embeddings))


def envelope_for(
    path: Path, *, highlight_text: str = "Duration measures sensitivity.", **overrides
) -> IngestionEnvelope:
    normalized = normalize_source(path.read_bytes(), "obsidian://duration")
    defaults = {
        "envelope_id": "env-1",
        "source_record_id": "source-1",
        "canonical_record_id": "source-1",
        "source_type": "obsidian",
        "origin": "obsidian://duration",
        "normalized_origin": "obsidian://duration",
        "captured_at": datetime.now(timezone.utc),
        "observed_at": None,
        "raw_content_ref": str(path),
        "raw_content_hash": normalized.raw_hash,
        "normalized_content_hash": normalized.normalized_hash,
        "highlight_index": 0,
        "highlight_text": highlight_text,
        "highlight_context_text": None,
        "highlight_start_char": 0,
        "highlight_end_char": len(highlight_text),
        "version": 1,
        "metadata": {"tags": ["fixed_income", "risk"]},
        "extracted_metadata": {"tag": "source-note"},
        "access_policy": AccessPolicy(),
        "extraction_version": "v1",
        "semantic": SemanticExtraction(field_tags=["duration", "risk"]),
        "model_confidence": 0.9,
        "review_status": "approved",
    }
    defaults.update(overrides)
    return IngestionEnvelope(**defaults)


def test_consumer_embeds_and_writes_complete_provenance(tmp_path: Path) -> None:
    raw = tmp_path / "source.raw"
    raw.write_text("---\ntags: imported\n---\nDuration measures sensitivity.\n", encoding="utf-8")
    envelope = envelope_for(raw)
    store = FakeVectorStore()
    embedder = FakeEmbeddingClient()

    artifact = VectorConsumer(store, embedding_client=embedder).consume(envelope)

    assert artifact == "chroma:knowledge:source=source-1:highlight=0:chunks=1"
    assert store.writable_checks == ["knowledge"]
    assert len(embedder.calls) == 1
    assert embedder.calls[0][1:] == ("retrieval_document", "ollama")
    collection, ids, texts, metadatas, embeddings = store.upserts[0]
    assert collection == "knowledge"
    assert ids == [f"{envelope.envelope_id}_0"]
    assert texts == ["Duration measures sensitivity."]
    assert len(embeddings[0]) == EMBEDDING_DIMENSION
    assert metadatas == [
        {
            "highlight_id": highlight_id_for_highlight("source-1", 0),
            "highlight_index": 0,
            "source_id": "source-1",
            "source_type": "obsidian",
            "tags": ["duration", "fixed_income", "risk", "source-note"],
            "envelope_id": "env-1",
            "raw_content_hash": envelope.raw_content_hash,
            "normalized_content_hash": envelope.normalized_content_hash,
            "version": 1,
            "chunk_index": 0,
            "chunk_total": 1,
            "chunk_start_char": 0,
            "chunk_end_char": len("Duration measures sensitivity."),
            "sentence_start": 0,
            "sentence_end": 1,
            "hard_split": False,
            "used_bounded_context": False,
            "selection_parent_source_ref": None,
            "selection_parent_start_char": None,
            "selection_parent_end_char": None,
        }
    ]


def test_consumer_purges_superseded_source_before_upsert(tmp_path: Path) -> None:
    raw = tmp_path / "source.raw"
    raw.write_text("Updated duration note.", encoding="utf-8")
    envelope = envelope_for(
        raw,
        source_record_id="source-2",
        canonical_record_id="source-2",
        supersedes_record_id="source-1",
        version=2,
    )
    store = FakeVectorStore()

    VectorConsumer(store, embedding_client=FakeEmbeddingClient()).consume(envelope)

    assert store.purges == [("knowledge", "source-1")]
    assert len(store.upserts) == 1


def test_gateway_fallback_is_rejected_without_purging_or_writing(tmp_path: Path) -> None:
    raw = tmp_path / "source.raw"
    raw.write_text("Updated duration note.", encoding="utf-8")
    envelope = envelope_for(raw, supersedes_record_id="source-old")
    store = FakeVectorStore()

    with pytest.raises(RuntimeError, match="cross-model fallback is disabled"):
        VectorConsumer(
            store,
            embedding_client=FakeEmbeddingClient(provider="gemini"),
        ).consume(envelope)

    assert store.purges == []
    assert store.upserts == []


def test_wrong_embedding_dimension_is_rejected(tmp_path: Path) -> None:
    raw = tmp_path / "source.raw"
    raw.write_text("Duration note.", encoding="utf-8")
    envelope = envelope_for(raw)
    store = FakeVectorStore()

    with pytest.raises(RuntimeError, match="expected 768"):
        VectorConsumer(
            store,
            embedding_client=FakeEmbeddingClient(dimension=10),
        ).consume(envelope)

    assert store.upserts == []


def test_hash_mismatch_is_rejected_before_gateway_call(tmp_path: Path) -> None:
    raw = tmp_path / "source.raw"
    raw.write_text("Duration note.", encoding="utf-8")
    envelope = envelope_for(raw, raw_content_hash="wrong")
    store = FakeVectorStore()
    embedder = FakeEmbeddingClient()

    with pytest.raises(RuntimeError, match="raw_content_hash"):
        VectorConsumer(store, embedding_client=embedder).consume(envelope)

    assert embedder.calls == []
    assert store.upserts == []


def test_empty_content_cannot_be_recorded_as_success(tmp_path: Path) -> None:
    raw = tmp_path / "source.raw"
    raw.write_text("", encoding="utf-8")
    envelope = envelope_for(raw)
    store = FakeVectorStore()

    with pytest.raises(RuntimeError, match="empty vector projection"):
        VectorConsumer(store, embedding_client=FakeEmbeddingClient()).consume(envelope)

    assert store.upserts == []


def test_chroma_failure_propagates_for_dispatch_retry(tmp_path: Path) -> None:
    raw = tmp_path / "source.raw"
    raw.write_text("Duration note.", encoding="utf-8")
    envelope = envelope_for(raw)

    with pytest.raises(RuntimeError, match="Chroma write failed"):
        VectorConsumer(
            FakeVectorStore(fail_upsert=True),
            embedding_client=FakeEmbeddingClient(),
        ).consume(envelope)


def test_invalid_chunk_boundaries_are_rejected() -> None:
    with pytest.raises(ValueError, match="sentence_overlap"):
        VectorConsumer(
            FakeVectorStore(),
            embedding_client=FakeEmbeddingClient(),
            chunk_config=EmbeddingChunkConfig(
                target_sentences=1,
                minimum_sentences=1,
                sentence_overlap=1,
            ),
        )


def test_fragment_selection_embeds_only_its_containing_sentence(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "selection.raw"
    raw.write_text("duration", encoding="utf-8")
    containing = "Bond duration measures interest-rate sensitivity."
    envelope = envelope_for(
        raw,
        highlight_text="duration",
        highlight_end_char=len("duration"),
        highlight_boundary_origin="user_selection",
        highlight_parent_source_ref="obsidian://bonds",
        highlight_parent_start_char=5,
        highlight_parent_end_char=13,
        highlight_containing_sentence=containing,
    )
    store = FakeVectorStore()
    embedder = FakeEmbeddingClient()

    VectorConsumer(store, embedding_client=embedder).consume(envelope)

    assert [call[0] for call in embedder.calls] == [containing]
    metadata = store.upserts[0][3][0]
    assert metadata["used_bounded_context"] is True
    assert metadata["selection_parent_start_char"] == 5
    assert metadata["selection_parent_end_char"] == 13
