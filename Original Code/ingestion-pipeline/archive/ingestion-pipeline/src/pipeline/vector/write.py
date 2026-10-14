"""Bronze -> Chroma ingestion step for the storage pipeline.

`write_vector` is the vector consumer's analog of the KG package's
extraction + ingestion: it reads a bronze item, chunks the body structurally,
and upserts the chunks into ChromaDB, recording the single ledger stage
``(vector, upserted)``.

Design (see vector-db/VECTOR_ALIGNMENT_PLAN.md):
  - Reads the *bronze* body, never a cleaned copy (P1).
  - Deterministic chunk IDs ``{content_hash}_{i}`` and a ``content_hash``
    provenance field on every chunk (P4/P6) — idempotent by construction.
  - One ledger stage, ``upserted`` (P11): nothing expensive is persisted, so
    there is no intermediate artifact to checkpoint.
  - Refuses to write with a fallback embedder; a failure is recorded in the
    ledger, never silently swallowed (P6/P7).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipeline.vector.ingestion import chunk_text

if TYPE_CHECKING:
    from pipeline.core.ledger import Item
    from pipeline.vector.vector_store import VectorStore

logger = logging.getLogger(__name__)

COLLECTION = "knowledge"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100


def write_vector(
    item: "Item",
    store: "VectorStore",
    collection: str = COLLECTION,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> None:
    """Chunk a bronze item and upsert it into ChromaDB. Idempotent.

    Marks ledger stage ``(vector, upserted)`` done on success, failed on error
    (and re-raises so the orchestrator can count/log it).
    """
    from pipeline.core.bronze import read_body
    from pipeline.core.ledger import is_done, mark

    if is_done(item.content_hash, "vector", "upserted"):
        logger.info("[write_vector] %s already upserted — skipping", item.item_id)
        return

    try:
        # P6/P7: never let ChromaDB fall back to a different embedder and mark
        # the item done with corrupt vectors. Checked before any write.
        store.ensure_embedder(collection)

        body = read_body(item.bronze_abs())
        if not body.strip():
            # Termination guarantee: an empty item must still leave the pending
            # set, or run_vector() would return it forever.
            logger.warning("[write_vector] %s has empty body — marking done, nothing to store", item.item_id)
            mark(item.content_hash, "vector", "upserted", "done")
            return

        chunks = chunk_text(body, chunk_size, chunk_overlap)
        total = len(chunks)
        chunk_ids = [f"{item.content_hash}_{i}" for i in range(total)]
        metadatas = [
            {
                # Frontmatter first so the authoritative provenance/locator fields below
                # always win — a capture with metadata={"source": "https://…"} must not
                # overwrite the ledger's source, content_hash, etc.
                **item.metadata,
                "content_hash": item.content_hash,  # provenance (P4) — vector analog of KG source_hash
                "item_id": item.item_id,
                "source": item.source,
                "captured_at": item.captured_at,
                "chunk_index": i,
                "chunk_total": total,
            }
            for i in range(total)
        ]

        # Clear any chunks from a prior run under a different chunk_size so a
        # shorter re-chunk doesn't leave stragglers. Deterministic IDs mean the
        # upsert itself is already idempotent for an unchanged chunk_size.
        store.delete_chunks_by_content_hash(collection, item.content_hash)
        store.upsert_batch(collection, chunk_ids, chunks, metadatas)

        mark(item.content_hash, "vector", "upserted", "done")
        logger.info("[write_vector] %s: %d chunk(s) upserted to %r", item.item_id, total, collection)
    except Exception as exc:
        mark(item.content_hash, "vector", "upserted", "failed", error=str(exc))
        logger.exception("[write_vector] %s FAILED: %s", item.item_id, exc)
        raise
