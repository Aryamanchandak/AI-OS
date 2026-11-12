from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.vector.vector_store import (
    EMBEDDING_DIMENSION,
    EMBEDDING_PROFILE,
    VectorStore,
    validate_embedding,
)


class FakeCollection:
    def __init__(self, name: str, metadata: dict | None = None) -> None:
        self.name = name
        self.metadata = metadata or {}
        self.upserts: list[dict] = []
        self.deletes: list[dict] = []

    def upsert(self, **kwargs) -> None:
        self.upserts.append(kwargs)

    def delete(self, **kwargs) -> None:
        self.deletes.append(kwargs)

    def query(self, **kwargs):
        return {
            "ids": [["id-1"]],
            "distances": [[0.2]],
            "metadatas": [[{"source_id": "source-1"}]],
            "documents": [["matched text"]],
        }

    def get(self, **kwargs):
        return {
            "ids": ["id-1"],
            "metadatas": [{"source_id": "source-1"}],
            "documents": ["matched text"],
        }


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def list_collections(self):
        return list(self.collections.values())

    def get_collection(self, *, name: str):
        return self.collections[name]

    def get_or_create_collection(self, *, name: str, metadata: dict):
        collection = self.collections.setdefault(name, FakeCollection(name, metadata))
        return collection


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def embed(self, text, task_type="retrieval_document", provider=None):
        self.calls.append((text, task_type, provider))
        return {
            "provider": "ollama",
            "model": "nomic-embed-text",
            "dim": EMBEDDING_DIMENSION,
            "embedding": [0.0] * EMBEDDING_DIMENSION,
        }


def valid_response() -> dict:
    return {
        "provider": "ollama",
        "model": "nomic-embed-text",
        "dim": EMBEDDING_DIMENSION,
        "embedding": [0.0] * EMBEDDING_DIMENSION,
    }


def test_validate_embedding_rejects_fallback_provider() -> None:
    response = valid_response()
    response["provider"] = "gemini"

    with pytest.raises(RuntimeError, match="cross-model fallback is disabled"):
        validate_embedding(response)


def test_validate_embedding_rejects_wrong_dimension() -> None:
    response = valid_response()
    response["dim"] = 3072

    with pytest.raises(RuntimeError, match="expected 768"):
        validate_embedding(response)


def test_upsert_uses_explicit_embeddings_and_complete_metadata(tmp_path: Path) -> None:
    client = FakeClient()
    store = VectorStore(tmp_path / "chroma", client=client)
    embedding = [0.0] * EMBEDDING_DIMENSION

    store.upsert_batch(
        "knowledge",
        ["hash_0"],
        ["source text"],
        [{"source_id": "source-1", "tags": ["alpha", "beta"], "version": 1}],
        [embedding],
    )

    collection = client.collections["knowledge"]
    assert collection.metadata["embedding_profile"] == EMBEDDING_PROFILE
    assert collection.upserts == [
        {
            "ids": ["hash_0"],
            "documents": ["source text"],
            "metadatas": [
                {"source_id": "source-1", "tags": "alpha,beta", "version": 1}
            ],
            "embeddings": [embedding],
        }
    ]


def test_upsert_rejects_wrong_dimension_before_touching_chroma(tmp_path: Path) -> None:
    client = FakeClient()
    store = VectorStore(tmp_path / "chroma", client=client)

    with pytest.raises(ValueError, match="dimension"):
        store.upsert_batch(
            "knowledge",
            ["id"],
            ["text"],
            [{"source_id": "source-1"}],
            [[0.0] * 10],
        )

    assert client.collections == {}


def test_existing_incompatible_collection_is_rejected(tmp_path: Path) -> None:
    client = FakeClient()
    client.collections["knowledge"] = FakeCollection(
        "knowledge",
        {"embedding_profile": "different-model:768"},
    )
    store = VectorStore(tmp_path / "chroma", client=client)

    with pytest.raises(RuntimeError, match="different-model"):
        store.ensure_writable("knowledge")


def test_delete_is_scoped_by_source_id(tmp_path: Path) -> None:
    client = FakeClient()
    client.collections["knowledge"] = FakeCollection(
        "knowledge",
        {"embedding_profile": EMBEDDING_PROFILE},
    )
    store = VectorStore(tmp_path / "chroma", client=client)

    store.delete_by_source_id("knowledge", "old-source")

    assert client.collections["knowledge"].deletes == [
        {"where": {"source_id": "old-source"}}
    ]


def test_search_embeds_query_through_pinned_ollama_gateway(tmp_path: Path) -> None:
    client = FakeClient()
    client.collections["knowledge"] = FakeCollection(
        "knowledge",
        {"embedding_profile": EMBEDDING_PROFILE},
    )
    embedder = FakeEmbedder()
    store = VectorStore(
        tmp_path / "chroma",
        client=client,
        embedding_client=embedder,
    )

    hits = store.search("knowledge", "duration risk")

    assert embedder.calls == [("duration risk", "retrieval_query", "ollama")]
    assert hits[0].id == "id-1"
    assert hits[0].score == pytest.approx(0.8)
