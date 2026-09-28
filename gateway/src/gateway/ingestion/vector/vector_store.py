"""Chroma vector store using explicit gateway-produced embeddings.

Writes fail loudly: this module never lets Chroma select a default embedding
function and never treats an unavailable store as a successful no-op.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import math
from pathlib import Path
from typing import Any, Protocol, Sequence

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 768
EMBEDDING_MODEL = "nomic-embed-text"
# The persisted Chroma vector-space identity, independent of which GLC task
# profile produced the vector. Never overload this with a profile name: one
# is a storage-compatibility fact, the other is a routing request.
EMBEDDING_PROFILE = f"{EMBEDDING_MODEL}:{EMBEDDING_DIMENSION}"
# The GLC task profile every ingestion embedding call requests. GLC owns
# which provider/model/dimension this resolves to.
EMBEDDING_GLC_PROFILE = "chunker-v1"


class EmbeddingClient(Protocol):
    def embed(
        self,
        text: str,
        task_type: str = "retrieval_document",
        profile: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, repr=False)
class SimilarityHit:
    id: str
    score: float
    metadata: dict[str, Any]
    text: str = ""

    def __repr__(self) -> str:
        preview = (self.text[:60] + "…") if len(self.text) > 60 else self.text
        return (
            f"SimilarityHit(id={self.id!r}, score={self.score:.3f}, "
            f"text={preview!r})"
        )


def validate_embedding(
    response: dict[str, Any],
    *,
    expected_model: str = EMBEDDING_MODEL,
    expected_dimension: int = EMBEDDING_DIMENSION,
) -> list[float]:
    """Validate one pinned-model gateway response and return its vector."""
    provider = response.get("provider")
    model = response.get("model")
    reported_dimension = response.get("dim")
    raw_embedding = response.get("embedding")

    if provider != "ollama":
        raise RuntimeError(
            f"Embedding provider must be 'ollama', received {provider!r}; "
            "cross-model fallback is disabled"
        )
    if model != expected_model:
        raise RuntimeError(
            f"Embedding model must be {expected_model!r}, received {model!r}"
        )
    if reported_dimension != expected_dimension:
        raise RuntimeError(
            f"Gateway reported embedding dimension {reported_dimension!r}; "
            f"expected {expected_dimension}"
        )
    if not isinstance(raw_embedding, list) or len(raw_embedding) != expected_dimension:
        actual = len(raw_embedding) if isinstance(raw_embedding, list) else None
        raise RuntimeError(
            f"Embedding vector has dimension {actual!r}; expected {expected_dimension}"
        )

    embedding: list[float] = []
    for value in raw_embedding:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError("Embedding vector contains a non-numeric value")
        number = float(value)
        if not math.isfinite(number):
            raise RuntimeError("Embedding vector contains a non-finite value")
        embedding.append(number)
    return embedding


class VectorStore:
    """Persistent Chroma wrapper that only accepts explicit embeddings."""

    def __init__(
        self,
        chroma_path: Path,
        *,
        embedding_client: EmbeddingClient | None = None,
        client: Any = None,
    ) -> None:
        self._path = chroma_path
        self._embedding_client = embedding_client
        self._client: Any = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "chromadb is not installed; install the vector dependency"
            ) from exc
        try:
            self._path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._path))
        except Exception as exc:
            raise RuntimeError(f"Cannot open ChromaDB at {self._path}: {exc}") from exc
        return self._client

    @staticmethod
    def _collection_names(client: Any) -> set[str]:
        try:
            return {
                collection if isinstance(collection, str) else str(collection.name)
                for collection in client.list_collections()
            }
        except Exception as exc:
            raise RuntimeError(f"Cannot list Chroma collections: {exc}") from exc

    @staticmethod
    def _assert_collection_profile(collection: Any, name: str) -> None:
        metadata = collection.metadata or {}
        stored_profile = metadata.get("embedding_profile")
        stored_model = metadata.get("embedding_model")
        stored_dimension = metadata.get("embedding_dimension")
        if stored_profile and stored_profile != EMBEDDING_PROFILE:
            raise RuntimeError(
                f"Collection {name!r} uses embedding profile {stored_profile!r}; "
                f"expected {EMBEDDING_PROFILE!r}"
            )
        if stored_model and stored_model != EMBEDDING_MODEL:
            raise RuntimeError(
                f"Collection {name!r} uses model {stored_model!r}; "
                f"expected {EMBEDDING_MODEL!r}"
            )
        if stored_dimension and stored_dimension != EMBEDDING_DIMENSION:
            raise RuntimeError(
                f"Collection {name!r} uses dimension {stored_dimension!r}; "
                f"expected {EMBEDDING_DIMENSION}"
            )

    def _get_collection(self, name: str, *, create: bool) -> Any | None:
        client = self._get_client()
        exists = name in self._collection_names(client)
        try:
            if exists:
                collection = client.get_collection(name=name)
            elif not create:
                return None
            else:
                collection = client.get_or_create_collection(
                    name=name,
                    metadata={
                        "hnsw:space": "cosine",
                        "embedding_profile": EMBEDDING_PROFILE,
                        "embedding_model": EMBEDDING_MODEL,
                        "embedding_dimension": EMBEDDING_DIMENSION,
                    },
                )
        except Exception as exc:
            raise RuntimeError(f"Cannot open Chroma collection {name!r}: {exc}") from exc
        self._assert_collection_profile(collection, name)
        return collection

    def ensure_writable(self, collection: str) -> None:
        """Raise unless Chroma is available and the collection is compatible."""
        self._get_collection(collection, create=True)

    @staticmethod
    def _safe_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
        safe: dict[str, str | int | float | bool] = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, bool):
                safe[key] = value
            elif isinstance(value, (str, int, float)):
                safe[key] = value
            elif isinstance(value, (list, tuple, set)):
                safe[key] = ",".join(str(item) for item in value)
            else:
                safe[key] = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return safe

    def upsert_batch(
        self,
        collection: str,
        ids: Sequence[str],
        texts: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Upsert documents and their already-generated gateway embeddings."""
        count = len(ids)
        if count == 0:
            raise ValueError("Refusing an empty vector upsert")
        if len(set(ids)) != count:
            raise ValueError("Vector IDs must be unique within a batch")
        if not (len(texts) == len(metadatas) == len(embeddings) == count):
            raise ValueError("IDs, texts, metadata, and embeddings must have equal lengths")
        if any(not text.strip() for text in texts):
            raise ValueError("Vector documents cannot be blank")

        checked_embeddings: list[list[float]] = []
        for embedding in embeddings:
            if len(embedding) != EMBEDDING_DIMENSION:
                raise ValueError(
                    f"Embedding dimension must be {EMBEDDING_DIMENSION}, "
                    f"received {len(embedding)}"
                )
            checked: list[float] = []
            for value in embedding:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("Embedding contains a non-numeric value")
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError("Embedding contains a non-finite value")
                checked.append(number)
            checked_embeddings.append(checked)

        chroma_collection = self._get_collection(collection, create=True)
        assert chroma_collection is not None
        try:
            chroma_collection.upsert(
                ids=list(ids),
                documents=list(texts),
                metadatas=[self._safe_metadata(metadata) for metadata in metadatas],
                embeddings=checked_embeddings,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Vector upsert failed for collection {collection!r}: {exc}"
            ) from exc

    def delete_by_source_id(self, collection: str, source_id: str) -> None:
        """Delete every vector projection belonging to one source record."""
        chroma_collection = self._get_collection(collection, create=False)
        if chroma_collection is None:
            return
        try:
            chroma_collection.delete(where={"source_id": source_id})
        except Exception as exc:
            raise RuntimeError(
                f"Could not purge source {source_id!r} from {collection!r}: {exc}"
            ) from exc

    def search(
        self,
        collection: str,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SimilarityHit]:
        """Search with a query embedding produced by the pinned gateway model."""
        if self._embedding_client is None:
            raise RuntimeError("Vector search requires an embedding gateway client")
        response = self._embedding_client.embed(
            query,
            task_type="retrieval_query",
            profile=EMBEDDING_GLC_PROFILE,
        )
        query_embedding = validate_embedding(response)
        chroma_collection = self._get_collection(collection, create=False)
        if chroma_collection is None:
            return []
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        try:
            return self._parse_query_result(chroma_collection.query(**kwargs))
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)
            return []

    def get(
        self,
        collection: str,
        *,
        where: dict[str, Any] | None = None,
        ids: list[str] | None = None,
    ) -> list[SimilarityHit]:
        chroma_collection = self._get_collection(collection, create=False)
        if chroma_collection is None:
            return []
        kwargs: dict[str, Any] = {"include": ["documents", "metadatas"]}
        if where:
            kwargs["where"] = where
        if ids:
            kwargs["ids"] = ids
        try:
            return self._parse_get_result(chroma_collection.get(**kwargs))
        except Exception as exc:
            logger.warning("Vector get failed: %s", exc)
            return []

    @staticmethod
    def _parse_query_result(result: dict[str, Any]) -> list[SimilarityHit]:
        hits: list[SimilarityHit] = []
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        documents = result.get("documents", [[]])[0]
        for index, document_id in enumerate(ids):
            distance = distances[index] if index < len(distances) else 2.0
            score = min(1.0, max(0.0, 1.0 - float(distance)))
            metadata = metadatas[index] if index < len(metadatas) else {}
            text = documents[index] if index < len(documents) else ""
            hits.append(
                SimilarityHit(
                    id=document_id,
                    score=score,
                    metadata=metadata or {},
                    text=text or "",
                )
            )
        return hits

    @staticmethod
    def _parse_get_result(result: dict[str, Any]) -> list[SimilarityHit]:
        hits: list[SimilarityHit] = []
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", []) or []
        documents = result.get("documents", []) or []
        for index, document_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            text = documents[index] if index < len(documents) else ""
            hits.append(
                SimilarityHit(
                    id=document_id,
                    score=1.0,
                    metadata=metadata or {},
                    text=text or "",
                )
            )
        return hits
