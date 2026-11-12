"""Ingestion pipeline for vector_db.

Accepts both raw documents (split into chunks) and pre-atomized items
(embedded as-is). The caller supplies an IngestDocument; this module handles
chunking, embedding via VectorStore, and error collection.
"""

import logging
import re
from typing import TYPE_CHECKING

from vector_db.models import IngestDocument, IngestResult

if TYPE_CHECKING:
    from vector_db.vector_store import VectorStore

logger = logging.getLogger(__name__)


def _hard_split(text: str, size: int) -> list[str]:
    """Last-resort: split at hard character boundary. No overlap."""
    logger.debug("hard_split — text_len=%d, size=%d", len(text), size)
    return [text[i : i + size] for i in range(0, len(text), size)]


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split *text* into overlapping chunks of at most *chunk_size* characters.

    Strategy:
      1. Split on blank lines (paragraph boundaries).
      2. If a paragraph exceeds *chunk_size*, split further on sentence ends.
      3. Any piece still exceeding *chunk_size* is hard-split at character
         boundaries as a last resort (handles code blocks, long URLs, tables).
      4. Accumulate pieces into chunks, flushing when the next piece would
         overflow.
      5. Prepend the last *overlap* characters of the previous chunk to each
         new chunk so context carries across boundaries.

    Returns a list of non-empty strings. Always returns at least one chunk.
    Callers must ensure *text* is non-empty.
    """
    logger.debug(
        "_chunk_text — text_len=%d, chunk_size=%d, overlap=%d", len(text), chunk_size, overlap
    )

    # Step 1 + 2: get sentence-level pieces
    sentence_end = re.compile(r'(?<=[.!?])\s+')
    pieces: list[str] = []
    paragraphs = re.split(r'\n\n+', text)
    logger.debug("  %d paragraph(s) found", len(paragraphs))
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= chunk_size:
            pieces.append(para)
        else:
            sentences = [s.strip() for s in sentence_end.split(para) if s.strip()]
            logger.debug(
                "  paragraph too long (%d chars) — split into %d sentence(s)",
                len(para), len(sentences),
            )
            pieces.extend(sentences)

    if not pieces:
        logger.debug("  no pieces extracted — returning full text as single chunk")
        return [text]

    # Step 3: hard-split any piece that still exceeds chunk_size
    final_pieces: list[str] = []
    hard_split_count = 0
    for piece in pieces:
        if len(piece) <= chunk_size:
            final_pieces.append(piece)
        else:
            sub = _hard_split(piece, chunk_size)
            hard_split_count += len(sub)
            final_pieces.extend(sub)
    if hard_split_count:
        logger.debug("  %d piece(s) needed hard-splitting", hard_split_count)
    pieces = final_pieces

    # Step 4 + 5: accumulate into chunks with overlap
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    tail = ""  # last `overlap` chars of the previous flushed chunk

    for piece in pieces:
        piece_len = len(piece)
        if current and current_len + 1 + piece_len > chunk_size:
            flushed = " ".join(current)
            chunks.append((tail + " " + flushed) if tail else flushed)
            tail = flushed[-overlap:] if overlap else ""
            current = []
            current_len = len(tail)
        current.append(piece)
        current_len += piece_len + (1 if current_len else 0)

    if current:
        flushed = " ".join(current)
        chunks.append((tail + " " + flushed) if tail else flushed)

    result = chunks if chunks else [text]
    logger.debug("  _chunk_text produced %d chunk(s)", len(result))
    return result


# Public alias — the storage ingestion path (write.py) reuses the exact same
# structural, deterministic chunker used by VectorIngester so both paths chunk
# bronze identically.
def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> list[str]:
    """Structurally chunk *text* (paragraph → sentence → hard-split, with overlap)."""
    return _chunk_text(text, chunk_size, overlap)


class VectorIngester:
    """Pipeline that takes IngestDocuments and writes them to a VectorStore.

    Parameters
    ----------
    store:
        The VectorStore that handles ChromaDB persistence and embeddings.
    chunk_size:
        Maximum characters per chunk when ``doc.chunk=True``. Default 1000.
    chunk_overlap:
        Characters of overlap between adjacent chunks. Default 100.
    """

    def __init__(
        self,
        store: "VectorStore",
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
    ) -> None:
        self._store = store
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        logger.info(
            "VectorIngester created — chunk_size=%d, chunk_overlap=%d",
            chunk_size, chunk_overlap,
        )
        print(
            f"[vector_db] VectorIngester ready.\n"
            f"  chunk_size   : {chunk_size}\n"
            f"  chunk_overlap: {chunk_overlap}"
        )

    def ingest(self, doc: IngestDocument) -> IngestResult:
        """Ingest one document.

        If ``doc.chunk`` is True the text is split into overlapping chunks and
        each chunk is stored as a separate vector. Otherwise the document is
        stored as a single vector.

        Returns an IngestResult describing success or failure.
        """
        logger.info(
            "ingest — id=%r, collection=%r, chunk=%s, text_len=%d",
            doc.id, doc.collection, doc.chunk, len(doc.text),
        )
        print(
            f"[vector_db] Ingesting id={doc.id!r} into collection={doc.collection!r} "
            f"(chunk={doc.chunk}, text_len={len(doc.text)})"
        )

        if not doc.text.strip():
            logger.warning("ingest skipped — doc id=%r has empty text", doc.id)
            print(f"[vector_db] SKIP: doc id={doc.id!r} has empty text — nothing to store.")
            return IngestResult(total=0, succeeded=0, failed=0)

        if doc.chunk:
            result = self._ingest_chunked(doc)
        else:
            result = self._ingest_single(doc)

        if result.ok:
            logger.info(
                "ingest OK — id=%r, total=%d, succeeded=%d",
                doc.id, result.total, result.succeeded,
            )
            print(f"[vector_db] OK — id={doc.id!r}: {result.succeeded}/{result.total} stored.")
        else:
            logger.warning(
                "ingest had errors — id=%r, failed=%d/%d, errors=%r",
                doc.id, result.failed, result.total, result.errors,
            )
            print(
                f"[vector_db] PARTIAL/FAIL — id={doc.id!r}: "
                f"{result.failed}/{result.total} failed.\n"
                f"  Errors: {result.errors}"
            )
        return result

    def ingest_batch(self, docs: list[IngestDocument]) -> IngestResult:
        """Ingest multiple documents, aggregating results into one IngestResult."""
        logger.info("ingest_batch — %d document(s)", len(docs))
        print(f"[vector_db] Batch ingest: {len(docs)} document(s) ...")
        total = succeeded = failed = 0
        errors: list[tuple[str, str]] = []

        for i, doc in enumerate(docs, 1):
            logger.debug("  [%d/%d] ingesting id=%r", i, len(docs), doc.id)
            r = self.ingest(doc)
            total += r.total
            succeeded += r.succeeded
            failed += r.failed
            errors.extend(r.errors)

        result = IngestResult(total=total, succeeded=succeeded, failed=failed, errors=errors)
        logger.info(
            "ingest_batch complete — total=%d, succeeded=%d, failed=%d",
            total, succeeded, failed,
        )
        print(
            f"[vector_db] Batch complete: {succeeded}/{total} stored"
            + (f", {failed} FAILED — see above for details." if failed else ".")
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ingest_single(self, doc: IngestDocument) -> IngestResult:
        logger.debug("_ingest_single — id=%r, collection=%r", doc.id, doc.collection)
        # Clean up any chunks from a previous chunked version of this document.
        self._store.delete_chunks(doc.collection, doc.id)
        try:
            self._store.upsert(
                collection=doc.collection,
                id=doc.id,
                text=doc.text,
                metadata=doc.metadata,
            )
            return IngestResult(total=1, succeeded=1, failed=0)
        except Exception as exc:
            logger.warning(
                "_ingest_single failed — id=%r: %s\n"
                "  Possible causes: Ollama not running, ChromaDB write error, disk full.",
                doc.id, exc,
            )
            print(
                f"[vector_db] ERROR storing id={doc.id!r}: {exc}\n"
                f"  Check: is Ollama running? (ollama serve)\n"
                f"  Check: is ChromaDB path writable?"
            )
            return IngestResult(total=1, succeeded=0, failed=1, errors=[(doc.id, str(exc))])

    def _ingest_chunked(self, doc: IngestDocument) -> IngestResult:
        logger.info(
            "_ingest_chunked — id=%r, text_len=%d, chunk_size=%d, overlap=%d",
            doc.id, len(doc.text), self._chunk_size, self._chunk_overlap,
        )
        # Delete previously stored chunks for this id so a re-ingested shorter
        # document doesn't leave stale chunks behind.
        self._store.delete_chunks(doc.collection, doc.id)
        # Also delete the bare single-vector if this doc was previously stored
        # as chunk=False (delete_chunks finds nothing in that case).
        self._store.delete(doc.collection, ids=[doc.id])

        chunks = _chunk_text(doc.text, self._chunk_size, self._chunk_overlap)
        total = len(chunks)
        logger.info("split id=%r into %d chunk(s)", doc.id, total)
        print(f"[vector_db]   → {total} chunk(s) for id={doc.id!r}")

        chunk_ids = [f"{doc.id}__chunk_{i}" for i in range(total)]
        chunk_metas = [
            {**doc.metadata, "parent_id": doc.id, "chunk_index": i, "chunk_total": total}
            for i in range(total)
        ]
        try:
            logger.debug("attempting batch upsert of %d chunks for id=%r", total, doc.id)
            self._store.upsert_batch(
                collection=doc.collection,
                ids=chunk_ids,
                texts=chunks,
                metadatas=chunk_metas,
            )
            return IngestResult(total=total, succeeded=total, failed=0)
        except Exception as exc:
            logger.warning(
                "Batch upsert failed for id=%r (%s) — falling back to per-chunk upsert",
                doc.id, exc,
            )
            print(
                f"[vector_db] Batch upsert failed ({exc}) — retrying chunk by chunk ..."
            )
            succeeded = failed = 0
            errors: list[tuple[str, str]] = []
            for idx, (chunk_id, chunk_text, chunk_meta) in enumerate(
                zip(chunk_ids, chunks, chunk_metas)
            ):
                try:
                    logger.debug("  per-chunk upsert [%d/%d] id=%r", idx + 1, total, chunk_id)
                    self._store.upsert(
                        collection=doc.collection,
                        id=chunk_id,
                        text=chunk_text,
                        metadata=chunk_meta,
                    )
                    succeeded += 1
                except Exception as exc2:
                    logger.warning(
                        "  per-chunk upsert FAILED [%d/%d] id=%r: %s",
                        idx + 1, total, chunk_id, exc2,
                    )
                    print(f"[vector_db]   FAIL chunk {idx + 1}/{total} ({chunk_id}): {exc2}")
                    errors.append((chunk_id, str(exc2)))
                    failed += 1
            logger.info(
                "per-chunk fallback complete — succeeded=%d, failed=%d", succeeded, failed
            )
            return IngestResult(total=total, succeeded=succeeded, failed=failed, errors=errors)
