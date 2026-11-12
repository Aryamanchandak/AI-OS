# vector_store.py — Technical Documentation

**Last updated:** 2026-07-05
**Language:** Python

---

## What This File Does (Plain English)

`vector_store.py` is a generic ChromaDB wrapper with no dependency on any domain package. It stores and retrieves arbitrary text documents as embeddings. Every method degrades gracefully when ChromaDB or Ollama is absent — writes no-op and reads return empty — so callers stay functional when the vector store is unavailable. Genuine errors that occur while ChromaDB *is* available are logged at WARNING (not swallowed silently).

---

## Constructor

```python
VectorStore(
    chroma_path: Path,
    embedding_model: str = "nomic-embed-text",
    ollama_base_url: str = "http://localhost:11434",
)
```

- `chroma_path` — directory where ChromaDB persists data. Created on first write.
- `embedding_model` — Ollama model name used for all embeds in this instance.
- `ollama_base_url` — base URL for the local Ollama server; embeddings are generated via `POST {ollama_base_url}/api/embeddings`.

No API key required. Embeddings run fully local via Ollama.

---

## Public Methods

| Signature | Behaviour |
|---|---|
| `upsert(collection, id, text, metadata)` | Store or replace one document. No-ops silently if unavailable. Raises on real ChromaDB errors so VectorIngester can record them. |
| `upsert_batch(collection, ids, texts, metadatas)` | Store or replace multiple docs in one ChromaDB call (single batch embed). Raises on failure so VectorIngester falls back to per-item. |
| `search(collection, query, top_k, where)` | Semantic similarity search; returns `list[SimilarityHit]` sorted by score descending. `where` is an optional ChromaDB metadata filter. Returns `[]` on error or unavailability. |
| `get(collection, where, ids)` | Fetch documents by metadata filter or ID list with no semantic query. All hits return `score=1.0`. Returns `[]` on error. |
| `delete_chunks(collection, parent_id)` | Delete all chunks stored under `parent_id` (matched via `{"parent_id": parent_id}` metadata filter). Used before re-ingesting a chunked document. |
| `delete(collection, ids)` | Delete documents by ID list. Used by VectorIngester when a doc switches from `chunk=False` to `chunk=True`. |
| `delete_chunks_by_content_hash(collection, content_hash)` | Delete all chunks stored for a bronze item (matched via `{"content_hash": ...}` metadata). Used by the storage `write_vector` path before re-upserting so a re-chunk under a changed chunk_size leaves no stragglers. |
| `is_available()` | Returns True if the ChromaDB client was created successfully. Does not probe the embedding function or Ollama — use a real upsert+search round-trip to verify end-to-end. |
| `ensure_embedder(collection)` | **Write-path guard (no network).** Raises unless ChromaDB is up, the Ollama embedding function actually built (never the silent fallback embedder), and any existing `collection` uses the same model. Called by `write_vector` before every upsert so corrupt vectors are never written and marked done (P6/P7). |
| `assert_writable(collection)` | `ensure_embedder` plus a live Ollama round-trip (a probe embed). For fail-fast at the start of a run; catches Ollama-installed-but-down, which `ensure_embedder` can't (the ChromaDB EF constructor is lazy). |

---

## Collection Conventions

- Collection names are caller-defined — `VectorStore` imposes no naming scheme.
- Recommended: use a single collection (e.g. `"knowledge"`) and distinguish sources via `source_type` in metadata. This lets you search everything in one call and filter when needed.
- Collections are created on first write with `hnsw:space=cosine` and `embedding_model` stored in collection metadata. The space setting only applies when a collection is first created; existing collections keep their original space.
- If a collection is opened with a different `embedding_model` than the one stored in its metadata, a loud WARNING is logged: `EMBEDDING MODEL MISMATCH in collection ...`. Searches will return wrong results in that state. Delete `chroma_path` to recreate collections under the new model.

---

## Embedding: Ollama / nomic-embed-text

- Uses `chromadb.utils.embedding_functions.OllamaEmbeddingFunction` (bundled with chromadb, requires `ollama>=0.6` Python package).
- Embedding function is **cached** — built once on first `_get_collection()` call, reused for all subsequent calls.
- If the Ollama embedding function cannot be built (Ollama down, model not pulled, `ollama` package missing), a loud WARNING is logged and `_get_ef()` returns `None`. ChromaDB then falls back to its default sentence-transformers embedder, which produces incompatible vectors — delete the collection and restart Ollama to recover cleanly.

---

## Graceful Degradation

Two distinct failure modes:

| Mode | Behaviour | Logged? |
|---|---|---|
| ChromaDB not installed (`import chromadb` fails) | `_available = False`; all methods short-circuit and return empty / no-op | No — intentionally silent |
| ChromaDB installed but operation fails | Methods catch exceptions, log at WARNING, return empty / no-op | Yes — `exc_info=True` |

`is_available()` returns False only in the first mode. A True result means the client was created; it does not guarantee embeddings work.

---

## Internal Helpers

| Name | What it does |
|---|---|
| `_chroma_available()` | Module-level: attempts `import chromadb`; returns True/False. |
| `_get_client()` | Returns (and caches in `_client`) the `chromadb.PersistentClient`. Sets `_available = False` on ImportError. |
| `_get_ef()` | Returns (and caches in `_ef`) an `OllamaEmbeddingFunction`. Logs WARNING loudly on failure, returns None. |
| `_get_collection(name)` | Gets or creates a named collection; checks embedding model mismatch; passes cached EF. Returns None on any failure. |
| `_parse_query_result(result)` | Converts a ChromaDB `query()` result to `list[SimilarityHit]`. Cosine distance `d ∈ [0,2]` → `score = clamp(1-d, 0, 1)`. |
| `_parse_get_result(result)` | Converts a ChromaDB `get()` result (flat lists, no distances) to `list[SimilarityHit]` at `score=1.0`. |

---

## How VectorIngester Uses VectorStore

- **Switching chunk direction** (`chunk=False → chunk=True`): `_ingest_chunked()` calls `delete_chunks()` (removes chunk-id vectors) then `delete()` (removes the bare single-vector that `delete_chunks` misses, since it has no `parent_id` metadata).
- **Batched writes**: `_ingest_chunked()` calls `upsert_batch()` for the full chunk list in one call. On failure it falls back to sequential `upsert()` calls per chunk.
- **Single writes**: `_ingest_single()` calls `upsert()` directly after `delete_chunks()`.

---

## Known Gaps

- **No rate limiting**: `upsert_batch` sends the full text list to Ollama in one call. Very large batches (hundreds of chunks) may time out or OOM the Ollama server. Split into smaller batches if this becomes a problem.
- **Cosine space only applies to new collections**: `get_or_create_collection` ignores the space argument for collections that already exist. A store created before the cosine setting was introduced will use L2 distance, making `1 - distance` wrong. Delete `chroma_path` to recreate.
- **`ollama` package required at runtime**: chromadb's `OllamaEmbeddingFunction` depends on the `ollama` Python package (`pip install ollama`). This is declared in `pyproject.toml` but must be installed for embeddings to work.

---

## Developer Notes

- Dependencies: `chromadb>=0.4.0`, `ollama>=0.6` (both in `pyproject.toml`).
- To check end-to-end availability: upsert a doc, search for it, confirm a hit returns — `is_available()` alone only checks the ChromaDB client.
- ChromaDB persists to `chroma_path`. Delete this directory to reset all embeddings and collection metadata.
- Collections are created lazily on first write.

**Constructor note**: embeddings are local via Ollama (`ollama_base_url`, default `nomic-embed-text`); there is no `openai_api_key` parameter. Any external caller passing `openai_api_key=` will get a `TypeError` — pass `ollama_base_url` instead.
