"""ChromaDB-backed vector store, chunking, and archived storage consumer.

``run_vector()`` reads bronze items routed to ``vector`` from the shared
ledger, chunks and embeds them, and upserts them to ChromaDB::

       RAW_DATA_ROOT=".../Database/Raw Data" python -m vector_db.run

The unused generic ``VectorIngester`` API has been retired. The merged pipeline
uses ``VectorConsumer`` and its own ``VectorStore`` instead.
"""

from pipeline.vector.ingestion import chunk_text
from pipeline.vector.models import SimilarityHit
from pipeline.vector.vector_store import VectorStore
from pipeline.vector.write import write_vector

__all__ = [
    "VectorStore",
    "SimilarityHit",
    "chunk_text",
    "write_vector",
]
