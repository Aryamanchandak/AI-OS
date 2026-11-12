"""vector_db — ChromaDB-backed vector store, chunking, and the storage consumer.

Two ways in:

1. **Storage pipeline (the aligned consumer).** ``run_vector()`` reads bronze
   items routed to ``vector`` from the shared ledger, chunks + embeds them, and
   upserts to ChromaDB. This is what the ingestion button triggers::

       RAW_DATA_ROOT=".../Database/Raw Data" python -m vector_db.run

   It depends on the shared core in ``Raw Data/lib`` (resolved via ``RAW_DATA_ROOT``).

2. **Generic library (used directly by e.g. study_system).** ``VectorStore`` +
   ``VectorIngester`` + ``IngestDocument`` embed/search arbitrary text with no
   dependency on any domain package::

       store = VectorStore(chroma_path=Path("./data/chroma"))  # Ollama nomic-embed-text
       hits = store.search("knowledge", "query text", top_k=5)

Embeddings are local via Ollama; no API key required.
"""

from vector_db.ingestion import VectorIngester, chunk_text
from vector_db.models import IngestDocument, IngestResult, SimilarityHit
from vector_db.vector_store import VectorStore
from vector_db.write import write_vector

__all__ = [
    "VectorStore",
    "VectorIngester",
    "IngestDocument",
    "IngestResult",
    "SimilarityHit",
    "chunk_text",
    "write_vector",
]
