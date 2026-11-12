"""Shared data classes for the vector_db package.

No external dependencies — safe to import from any system.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IngestDocument:
    """A document to be embedded and stored in ChromaDB.

    Parameters
    ----------
    id:
        Caller-supplied stable identifier. Used as the ChromaDB upsert key.
        For chunked documents, chunk IDs are derived as ``{id}__chunk_{i}``.
        Re-ingesting the same id with ``chunk=True`` first deletes the old
        chunks, so revisions don't leave stale vectors behind.
    text:
        The content to embed. May be a short fact/snippet or a large document.
    collection:
        Name of the ChromaDB collection to store into. Created on first write.
        Recommended: use a single collection (e.g. ``"knowledge"``) and
        distinguish sources via ``source_type`` in metadata — this lets you
        search everything in one call and filter when needed.
    metadata:
        Key-value pairs stored alongside the embedding.

        Recommended fields (all optional, all scalar)::

            source_type : str   "textbook" | "article" | "book" | "note" | "highlight"
            title       : str   Document or chapter title
            author      : str   Author name(s)
            year        : int   Publication year
            domain      : str   Subject area, e.g. "equity", "fixed_income", "macro"
            url         : str   Source URL (for web articles)
            page        : int   Page number (for books/textbooks)
            chapter     : str   Chapter or section name
            tags        : str   Comma-joined topic tags, e.g. "capm,beta,risk"

        ChromaDB only accepts scalar values (str, int, float, bool).
        Lists are automatically coerced to comma-joined strings on write —
        e.g. ``tags=["capm","beta"]`` becomes ``"capm,beta"``. Such fields
        are retrievable but *not* filterable by individual element: a
        ``where={"tags": "capm"}`` filter will not match ``"capm,beta"``.
        Use scalar fields like ``source_type`` and ``domain`` for filtering.
    chunk:
        If True, ``text`` is split into overlapping chunks before embedding.
        Each chunk is stored as a separate vector with the parent ``id`` and
        ``chunk_index`` added to its metadata. Set to False (default) when
        the text is already small enough to embed as a single vector.

        Scale note: chunks are embedded locally via Ollama. ``upsert_batch``
        sends the whole chunk list in one call; very large documents still
        produce many embeddings, so split extreme batches if Ollama OOMs.
    """

    id: str
    text: str
    collection: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk: bool = False


@dataclass
class IngestResult:
    """Summary of a completed ingestion run."""

    total: int
    succeeded: int
    failed: int
    errors: list[tuple[str, str]] = field(default_factory=list)  # (id, error_message)

    @property
    def ok(self) -> bool:
        """True when every document was stored without error."""
        return self.failed == 0

    def __repr__(self) -> str:
        status = "ok" if self.ok else f"{self.failed} errors"
        return f"IngestResult(total={self.total}, succeeded={self.succeeded}, {status})"


@dataclass(frozen=True, repr=False)
class SimilarityHit:
    """A single result from a vector similarity search."""

    id: str
    score: float
    metadata: dict[str, Any]
    text: str = ""

    def __repr__(self) -> str:
        preview = (self.text[:60] + "…") if len(self.text) > 60 else self.text
        return f"SimilarityHit(id={self.id!r}, score={self.score:.3f}, text={preview!r})"
