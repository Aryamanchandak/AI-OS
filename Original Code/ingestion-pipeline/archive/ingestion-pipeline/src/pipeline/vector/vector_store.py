"""ChromaDB vector store — generic, no domain-type dependencies.

Every method degrades gracefully when ChromaDB is absent or broken:
  - write methods: no-op
  - read methods: return empty list / None
Genuine errors (ChromaDB *is* available but fails) are logged at WARNING.

All chromadb imports are lazy (inside method bodies only) so the module
imports cleanly even when chromadb is absent.

Collections are created with cosine distance (hnsw:space=cosine) so that
similarity scores from ``search()`` fall in [0, 1]. This only applies when
a collection is first created; existing collections keep whatever space
they were originally created with.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.vector.models import SimilarityHit

logger = logging.getLogger(__name__)


def _chroma_available() -> bool:
    try:
        import chromadb  # noqa: F401
        return True
    except ImportError:
        return False


class VectorStore:
    """Generic ChromaDB wrapper.

    Parameters
    ----------
    chroma_path:
        Directory where ChromaDB persists its data.
    embedding_model:
        Ollama embedding model name (e.g. ``'nomic-embed-text'``).
    ollama_base_url:
        Base URL for the local Ollama server.
    """

    def __init__(
        self,
        chroma_path: Path,
        embedding_model: str = "nomic-embed-text",
        ollama_base_url: str = "http://localhost:11434",
    ) -> None:
        self._path = chroma_path
        self._embedding_model = embedding_model
        self._ollama_base_url = ollama_base_url
        self._client: Any = None
        self._ef: Any = None
        self._available = _chroma_available()

        if not self._available:
            print(
                "[vector_db] WARNING: chromadb is not installed. "
                "All store operations will be no-ops.\n"
                "  Fix: pip install chromadb"
            )
            logger.warning(
                "chromadb is not installed — VectorStore is inert. Fix: pip install chromadb"
            )
        else:
            print(
                f"[vector_db] VectorStore initialised.\n"
                f"  chroma_path    : {chroma_path}\n"
                f"  embedding_model: {embedding_model}\n"
                f"  ollama_url     : {ollama_base_url}"
            )
            logger.info(
                "VectorStore created — chroma_path=%s, model=%s, ollama=%s",
                chroma_path, embedding_model, ollama_base_url,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert(
        self,
        collection: str,
        id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> None:
        """Upsert a single document into *collection*.

        No-ops silently when ChromaDB is unavailable and raises on genuine
        ChromaDB failures.
        """
        logger.debug("upsert — collection=%r, id=%r, text_len=%d", collection, id, len(text))
        col = self._get_collection(collection)
        if col is None:
            logger.warning("upsert skipped for %r — collection unavailable", id)
            return
        safe_meta: dict[str, Any] = {}
        for k, v in metadata.items():
            if v is None:
                continue
            safe_meta[k] = ",".join(str(x) for x in v) if isinstance(v, list) else v
        kwargs: dict[str, Any] = {"ids": [id], "documents": [text]}
        if safe_meta:
            kwargs["metadatas"] = [safe_meta]
        col.upsert(**kwargs)
        logger.info("upserted id=%r into collection=%r", id, collection)

    def upsert_batch(
        self,
        collection: str,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Upsert multiple documents in one ChromaDB call.

        ChromaDB passes the full list to the embedding function which batches
        the embed calls — far fewer Ollama calls than looping upsert().
        Raises on failure so the caller can record a failed write.
        """
        n = len(ids)
        logger.info("upsert_batch — collection=%r, count=%d", collection, n)
        print(f"[vector_db] Embedding and storing {n} chunk(s) into collection={collection!r} ...")
        col = self._get_collection(collection)
        if col is None:
            logger.warning("upsert_batch skipped — collection %r unavailable", collection)
            return
        safe_metas = []
        for metadata in metadatas:
            safe_meta: dict[str, Any] = {}
            for k, v in metadata.items():
                if v is None:
                    continue
                safe_meta[k] = ",".join(str(x) for x in v) if isinstance(v, list) else v
            safe_metas.append(safe_meta)
        kwargs: dict[str, Any] = {"ids": ids, "documents": texts}
        if any(safe_metas):
            kwargs["metadatas"] = safe_metas
        col.upsert(**kwargs)
        logger.info("upsert_batch complete — %d docs into collection=%r", n, collection)
        print(f"[vector_db] Stored {n} chunk(s) OK.")

    def search(
        self,
        collection: str,
        query: str,
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> list[SimilarityHit]:
        """Similarity search in *collection*.

        Parameters
        ----------
        collection:
            ChromaDB collection name.
        query:
            Query text — embedded on the fly using the same embedding function
            as the stored documents.
        top_k:
            Number of results to return.
        where:
            Optional ChromaDB metadata filter dict, e.g.
            ``{"domain": "equity"}``.

        Returns an empty list when ChromaDB is unavailable or the collection
        does not exist.
        """
        logger.info(
            "search — collection=%r, top_k=%d, filter=%r, query=%r",
            collection, top_k, where, query[:80],
        )
        col = self._get_collection(collection)
        if col is None:
            logger.warning("search skipped — collection %r unavailable", collection)
            return []
        try:
            kwargs: dict[str, Any] = {"query_texts": [query], "n_results": top_k}
            if where:
                kwargs["where"] = where
            result = col.query(**kwargs)
            hits = self._parse_query_result(result)
            logger.info("search returned %d hit(s) from collection=%r", len(hits), collection)
            if hits:
                logger.debug(
                    "top hit: id=%r, score=%.3f, text=%r",
                    hits[0].id, hits[0].score, hits[0].text[:60],
                )
            else:
                logger.debug("no hits — collection may be empty or query too dissimilar")
            return hits
        except Exception:
            logger.warning(
                "search failed in %r for query %r", collection, query, exc_info=True
            )
            print(
                f"[vector_db] ERROR: search failed in collection={collection!r}. "
                "Check logs for details."
            )
            return []

    def get(
        self,
        collection: str,
        where: Optional[dict[str, Any]] = None,
        ids: Optional[list[str]] = None,
    ) -> list[SimilarityHit]:
        """Fetch documents by metadata filter or ID list without a semantic query.

        All returned hits have score=1.0. Used for neighbor-chunk expansion and
        filter-only retrieval.
        """
        logger.debug("get — collection=%r, where=%r, ids=%r", collection, where, ids)
        col = self._get_collection(collection)
        if col is None:
            logger.warning("get skipped — collection %r unavailable", collection)
            return []
        try:
            kwargs: dict[str, Any] = {"include": ["documents", "metadatas"]}
            if where:
                kwargs["where"] = where
            if ids:
                kwargs["ids"] = ids
            result = col.get(**kwargs)
            hits = self._parse_get_result(result)
            logger.debug("get returned %d doc(s) from collection=%r", len(hits), collection)
            return hits
        except Exception:
            logger.warning("get failed in %r", collection, exc_info=True)
            return []

    def delete_chunks(self, collection: str, parent_id: str) -> None:
        """Delete all chunks previously stored under *parent_id*.

        Retained for compatibility with stored chunks that use ``parent_id``.
        No-ops silently when ChromaDB is unavailable or there are no matches.
        """
        logger.debug("delete_chunks — collection=%r, parent_id=%r", collection, parent_id)
        col = self._get_collection(collection)
        if col is None:
            return
        try:
            col.delete(where={"parent_id": parent_id})
            logger.info("deleted chunks for parent_id=%r from collection=%r", parent_id, collection)
        except Exception:
            logger.warning(
                "delete_chunks failed for parent %r in %r", parent_id, collection, exc_info=True
            )

    def delete(self, collection: str, ids: list[str]) -> None:
        """Delete documents by ID.

        Retained as the store's explicit ID-based deletion operation.
        """
        logger.debug("delete — collection=%r, ids=%r", collection, ids)
        col = self._get_collection(collection)
        if col is None:
            return
        try:
            col.delete(ids=ids)
            logger.info("deleted %d id(s) from collection=%r", len(ids), collection)
        except Exception:
            logger.warning(
                "delete by ids failed in %r for ids %r", collection, ids, exc_info=True
            )

    def is_available(self) -> bool:
        """Return True if ChromaDB is installed and the client can be created."""
        available = self._get_client() is not None
        logger.debug("is_available() -> %s", available)
        return available

    # ------------------------------------------------------------------
    # Write-path safety (P6/P7)
    # ------------------------------------------------------------------
    #
    # The read path degrades gracefully (no-op / empty). The *ingestion* write
    # path must not: if the Ollama embedding function fails to build, ChromaDB
    # silently substitutes its own default embedder, producing wrong-dimensioned
    # vectors that get marked "done" in the ledger. On the write path we refuse
    # to proceed instead. `ensure_embedder` is the cheap per-item guard (no
    # network); `assert_writable` adds a one-shot Ollama round-trip for fail-fast
    # at the start of a run.

    def ensure_embedder(self, collection: str) -> None:
        """Raise unless a real embedding write can happen (no network probe).

        Guards the corruption path: ChromaDB up, the Ollama embedding function
        actually built (never None → never the silent fallback embedder), and —
        if *collection* already exists — it was built with the same model so we
        don't mix vector spaces.
        """
        client = self._get_client()
        if client is None:
            raise RuntimeError(
                f"ChromaDB unavailable at {self._path}. Refusing to write. "
                "Fix: ensure the path is writable and chromadb is installed."
            )
        if self._get_ef() is None:
            raise RuntimeError(
                f"Ollama embedding function ({self._embedding_model} @ "
                f"{self._ollama_base_url}) could not be built. Refusing to write — "
                "ChromaDB would fall back to a different embedder and corrupt the "
                f"collection. Fix: `ollama serve` and `ollama pull {self._embedding_model}`."
            )
        try:
            existing = [c.name for c in client.list_collections()]
        except Exception as exc:
            raise RuntimeError(
                f"ChromaDB could not list collections at {self._path}: {exc}. Refusing to write."
            ) from exc
        if collection in existing:
            try:
                stored = (client.get_collection(collection).metadata or {}).get("embedding_model")
            except Exception:
                stored = None
            if stored and stored != self._embedding_model:
                raise RuntimeError(
                    f"Collection {collection!r} was built with embedding_model={stored!r} but "
                    f"this store uses {self._embedding_model!r}. Writing would mix vector spaces. "
                    f"Fix: delete {self._path} to rebuild, or use the original model."
                )

    def assert_writable(self, collection: str) -> None:
        """`ensure_embedder` plus a live Ollama round-trip. Call once per run.

        Fails the whole run fast (before touching any item) when Ollama is
        installed-but-down, which `ensure_embedder` alone can't detect because
        the ChromaDB embedding-function constructor is lazy.
        """
        self.ensure_embedder(collection)
        ef = self._get_ef()
        try:
            probe = ef(["storage writability probe"])
        except Exception as exc:
            raise RuntimeError(
                f"Ollama did not return an embedding ({self._embedding_model} @ "
                f"{self._ollama_base_url}): {exc}. Refusing to write. "
                f"Fix: `ollama serve` and `ollama pull {self._embedding_model}`."
            ) from exc
        if not probe or probe[0] is None or len(probe[0]) == 0:
            raise RuntimeError(
                f"Ollama returned an empty embedding for model {self._embedding_model!r} — "
                "refusing to write."
            )
        logger.info("assert_writable OK — collection=%r, embed_dim=%d", collection, len(probe[0]))

    def delete_chunks_by_content_hash(self, collection: str, content_hash: str) -> None:
        """Delete all chunks stored for a bronze item, keyed on ``content_hash``.

        Called before re-upserting so a re-chunk under a changed chunk_size does
        not leave stale chunks behind. No-ops when the store is unavailable.
        """
        col = self._get_collection(collection)
        if col is None:
            return
        try:
            col.delete(where={"content_hash": content_hash})
            logger.info(
                "deleted chunks for content_hash=%r from collection=%r", content_hash, collection
            )
        except Exception:
            logger.warning(
                "delete_chunks_by_content_hash failed for %r in %r",
                content_hash, collection, exc_info=True,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        if not self._available:
            return None
        if self._client is not None:
            return self._client
        try:
            import chromadb
            logger.info("Connecting to ChromaDB at %s", self._path)
            print(f"[vector_db] Connecting to ChromaDB at {self._path} ...")
            self._client = chromadb.PersistentClient(path=str(self._path))
            logger.info("ChromaDB client ready at %s", self._path)
            print(f"[vector_db] ChromaDB connected OK.")
            return self._client
        except ImportError:
            self._available = False
            logger.error(
                "chromadb not importable despite earlier check — Fix: pip install chromadb"
            )
            return None
        except Exception:
            logger.error(
                "Failed to create ChromaDB client at %s. "
                "Check that the path is writable and not corrupted. "
                "To reset: delete the directory at that path.",
                self._path,
                exc_info=True,
            )
            print(
                f"[vector_db] ERROR: could not open ChromaDB at {self._path}.\n"
                f"  - Is the path writable?\n"
                f"  - Is another process locking it?\n"
                f"  - To reset: rm -rf {self._path}"
            )
            return None

    def _get_ef(self) -> Any:
        if self._ef is not None:
            return self._ef
        try:
            from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
            logger.info(
                "Building Ollama embedding function — model=%r, url=%s",
                self._embedding_model, self._ollama_base_url,
            )
            self._ef = OllamaEmbeddingFunction(
                url=f"{self._ollama_base_url}/api/embeddings",
                model_name=self._embedding_model,
            )
            logger.info("Ollama embedding function ready — model=%r", self._embedding_model)
            print(
                f"[vector_db] Ollama embedding function ready.\n"
                f"  model : {self._embedding_model}\n"
                f"  url   : {self._ollama_base_url}"
            )
            return self._ef
        except Exception:
            logger.warning(
                "Could not build Ollama embedding function for model %r at %s.\n"
                "  Fix:\n"
                "    1. Start Ollama:          ollama serve\n"
                "    2. Pull the model:        ollama pull %s\n"
                "    3. Verify it's running:   curl %s/api/tags",
                self._embedding_model,
                self._ollama_base_url,
                self._embedding_model,
                self._ollama_base_url,
                exc_info=True,
            )
            print(
                f"[vector_db] WARNING: Ollama embedding function failed to initialise.\n"
                f"  model : {self._embedding_model}\n"
                f"  url   : {self._ollama_base_url}\n"
                f"  Fix:\n"
                f"    1. ollama serve\n"
                f"    2. ollama pull {self._embedding_model}\n"
                f"    3. curl {self._ollama_base_url}/api/tags   (to verify)"
            )
            return None

    def _get_collection(self, name: str) -> Any:
        client = self._get_client()
        if client is None:
            return None
        try:
            ef = self._get_ef()
            existing_collections = [c.name for c in client.list_collections()]
            if name in existing_collections:
                logger.debug("collection %r exists — retrieving", name)
                existing = client.get_collection(name)
                stored_model = existing.metadata.get("embedding_model")
                if stored_model and stored_model != self._embedding_model:
                    msg = (
                        f"EMBEDDING MODEL MISMATCH in collection {name!r}: "
                        f"stored={stored_model!r}, current={self._embedding_model!r}. "
                        f"Search results WILL BE WRONG. "
                        f"Fix: delete chroma_path ({self._path}) to recreate collections."
                    )
                    logger.warning(msg)
                    print(f"[vector_db] WARNING: {msg}")
            else:
                logger.info("collection %r does not exist — will create it", name)
                print(f"[vector_db] Creating new collection {name!r} ...")
            kwargs: dict[str, Any] = {
                "name": name,
                "metadata": {"hnsw:space": "cosine", "embedding_model": self._embedding_model},
            }
            if ef is not None:
                kwargs["embedding_function"] = ef
            col = client.get_or_create_collection(**kwargs)
            count = col.count()
            logger.info(
                "collection %r ready — %d document(s) currently stored", name, count
            )
            return col
        except Exception:
            logger.warning(
                "Could not get/create collection %r.\n"
                "  Possible causes: ChromaDB version mismatch, corrupted DB, disk full.",
                name,
                exc_info=True,
            )
            print(
                f"[vector_db] ERROR: could not open/create collection {name!r}.\n"
                f"  Check logs for the full traceback."
            )
            return None

    @staticmethod
    def _parse_query_result(result: dict[str, Any]) -> list[SimilarityHit]:
        """Convert a ChromaDB query result to SimilarityHits.

        Collections use cosine space, so ChromaDB returns cosine distance in
        [0, 2] where 0 == identical. Exposed score = 1 - distance, clamped
        to [0, 1]. The matched text is included in each hit.
        """
        hits: list[SimilarityHit] = []
        ids_list = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        documents = result.get("documents", [[]])[0]

        for i, doc_id in enumerate(ids_list):
            dist = distances[i] if i < len(distances) else 2.0
            score = min(1.0, max(0.0, 1.0 - dist))
            meta = metadatas[i] if i < len(metadatas) else {}
            text = documents[i] if i < len(documents) else ""
            hits.append(SimilarityHit(id=doc_id, score=score, metadata=meta or {}, text=text or ""))
        return hits

    @staticmethod
    def _parse_get_result(result: dict[str, Any]) -> list[SimilarityHit]:
        """Convert a ChromaDB get() result (no distances) to SimilarityHits at score 1.0."""
        hits: list[SimilarityHit] = []
        ids_list = result.get("ids", [])
        metadatas = result.get("metadatas", []) or []
        documents = result.get("documents", []) or []
        for i, doc_id in enumerate(ids_list):
            meta = metadatas[i] if i < len(metadatas) else {}
            text = documents[i] if i < len(documents) else ""
            hits.append(SimilarityHit(
                id=doc_id, score=1.0, metadata=meta or {}, text=text or ""
            ))
        return hits
