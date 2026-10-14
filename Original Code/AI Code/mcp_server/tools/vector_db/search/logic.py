from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from vector_db.vector_store import VectorStore


def _store() -> VectorStore:
    chroma_path = os.environ.get("CHROMA_PATH", "").strip()
    if not chroma_path:
        raise RuntimeError("CHROMA_PATH env var must be set to the Chroma persistence directory")
    return VectorStore(chroma_path=Path(chroma_path).expanduser(), embedding_model="nomic-embed-text")


def _hit_to_dict(hit: Any) -> dict[str, Any]:
    return {
        "id": hit.id,
        "score": hit.score,
        "metadata": hit.metadata,
        "text": hit.text,
    }


def vector_db_search(
    query: str,
    collection: str,
    top_k: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    store = _store()
    return [_hit_to_dict(hit) for hit in store.search(collection=collection, query=query, top_k=top_k, where=where)]


def vector_db_get(
    collection: str,
    ids: list[str] | None = None,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    store = _store()
    return [_hit_to_dict(hit) for hit in store.get(collection=collection, ids=ids, where=where)]
