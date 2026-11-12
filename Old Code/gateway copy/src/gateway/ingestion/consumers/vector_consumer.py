"""Bridge from an approved ingestion envelope to the Chroma projection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gateway.ingestion.config import EmbeddingChunkConfig
from gateway.ingestion.ids import highlight_id_for_highlight
from gateway.ingestion.models import IngestionEnvelope
from gateway.ingestion.normalization import normalize_source
from gateway.ingestion.vector.chunking import sentence_chunks
from gateway.ingestion.vector.vector_store import (
    EMBEDDING_DIMENSION,
    EMBEDDING_GLC_PROFILE,
    EMBEDDING_MODEL,
    EmbeddingClient,
    VectorStore,
    validate_embedding,
)

COLLECTION = "knowledge"


def _tag_values(envelope: IngestionEnvelope) -> list[str]:
    tags = {tag.strip() for tag in envelope.semantic.field_tags if tag.strip()}
    for metadata in (envelope.extracted_metadata, envelope.metadata):
        for key in ("tag", "tags"):
            value = metadata.get(key)
            if isinstance(value, str):
                tags.update(part.strip() for part in value.split(",") if part.strip())
            elif isinstance(value, (list, tuple, set)):
                tags.update(str(part).strip() for part in value if str(part).strip())
    return sorted(tags)


class VectorConsumer:
    """`EnvelopeConsumer` implementation for the `vector` target."""

    target = "vector"

    def __init__(
        self,
        store: VectorStore,
        *,
        embedding_client: EmbeddingClient,
        collection: str = COLLECTION,
        chunk_config: EmbeddingChunkConfig | None = None,
    ) -> None:
        policy = chunk_config or EmbeddingChunkConfig()
        policy.validate()
        self.store = store
        self.embedding_client = embedding_client
        self.collection = collection
        self.chunk_config = policy

    def consume(self, envelope: IngestionEnvelope) -> str:
        if envelope.review_status not in {"approved", "not_required"}:
            raise ValueError("VectorConsumer only accepts approved envelopes")

        raw_path = Path(envelope.raw_content_ref)
        if not raw_path.is_file():
            raise RuntimeError(f"Immutable raw content is missing: {raw_path}")
        normalized = normalize_source(raw_path.read_bytes(), envelope.origin)
        if normalized.raw_hash != envelope.raw_content_hash:
            raise RuntimeError("Immutable raw content does not match raw_content_hash")
        if normalized.normalized_hash != envelope.normalized_content_hash:
            raise RuntimeError(
                "Immutable raw content does not match normalized_content_hash"
            )
        if not normalized.normalized_content.strip():
            raise RuntimeError("Refusing to mark an empty vector projection successful")

        uses_bounded_context = (
            envelope.highlight_boundary_origin == "user_selection"
            and envelope.highlight_containing_sentence is not None
            and not envelope.highlight_text.rstrip().endswith((".", "!", "?"))
        )
        vector_text = (
            envelope.highlight_containing_sentence
            if uses_bounded_context
            else envelope.highlight_text
        )
        assert vector_text is not None
        vector_chunks = sentence_chunks(vector_text, self.chunk_config)
        if not vector_chunks:
            raise RuntimeError("Refusing to mark an empty vector projection successful")
        chunks = [chunk.text for chunk in vector_chunks]
        highlight_id = highlight_id_for_highlight(
            envelope.source_record_id, envelope.highlight_index
        )
        # Keyed on the envelope, not the document hash: sibling highlights share
        # one `normalized_content_hash`, so hashing the document would give
        # every highlight the same chunk-0 id and each write would silently
        # overwrite the last.
        chunk_ids = [
            f"{envelope.envelope_id}_{index}" for index in range(len(chunks))
        ]

        self.store.ensure_writable(self.collection)
        embeddings: list[list[float]] = []
        for chunk in chunks:
            response = self.embedding_client.embed(
                chunk,
                task_type="retrieval_document",
                profile=EMBEDDING_GLC_PROFILE,
            )
            embeddings.append(
                validate_embedding(
                    response,
                    expected_model=EMBEDDING_MODEL,
                    expected_dimension=EMBEDDING_DIMENSION,
                )
            )

        tags = _tag_values(envelope)
        metadatas: list[dict[str, Any]] = [
            {
                "highlight_id": highlight_id,
                "highlight_index": envelope.highlight_index,
                "source_id": envelope.source_record_id,
                "source_type": envelope.source_type,
                "tags": tags,
                "envelope_id": envelope.envelope_id,
                "raw_content_hash": envelope.raw_content_hash,
                "normalized_content_hash": envelope.normalized_content_hash,
                "version": envelope.version,
                "chunk_index": index,
                "chunk_total": len(chunks),
                "chunk_start_char": vector_chunks[index].start_char,
                "chunk_end_char": vector_chunks[index].end_char,
                "sentence_start": vector_chunks[index].sentence_start,
                "sentence_end": vector_chunks[index].sentence_end,
                "hard_split": vector_chunks[index].hard_split,
                "used_bounded_context": uses_bounded_context,
                "selection_parent_source_ref": envelope.highlight_parent_source_ref,
                "selection_parent_start_char": envelope.highlight_parent_start_char,
                "selection_parent_end_char": envelope.highlight_parent_end_char,
            }
            for index in range(len(chunks))
        ]

        if envelope.supersedes_record_id:
            self.store.delete_by_source_id(
                self.collection,
                envelope.supersedes_record_id,
            )
        self.store.upsert_batch(
            self.collection,
            chunk_ids,
            chunks,
            metadatas,
            embeddings,
        )
        return (
            f"chroma:{self.collection}:source={envelope.source_record_id}"
            f":highlight={envelope.highlight_index}:chunks={len(chunks)}"
        )
