"""
Document indexing and knowledge-base search tools.

`index_document` chunks a sandbox file (or artifact) and writes every chunk
into the shared Memory service as a searchable `fact`. The chunks are embedded
via the V7 gateway so later vector searches can find them.

`search_knowledge` runs a vector query over those indexed facts and returns the
top-k ranked chunks with provenance.

Both tools import `memory` from the Lecture-7-copy path bootstrapped in
mcp_server.py — the same JSON + FAISS state shared with the main agent process.
"""
from __future__ import annotations

from datetime import datetime

import memory as _memory
import artifacts as _artifacts
from sandbox import _safe
from tool_registry import register


def _read_for_index(path: str) -> tuple[str, str]:
    """Return (text, source_label) for a sandbox file or artifact handle."""
    if path.startswith("art:"):
        blob = _artifacts.get_bytes(path)
        return blob.decode("utf-8", errors="replace"), path
    p = _safe(path)
    return p.read_text(encoding="utf-8"), f"sandbox:{path}"


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Sliding-window character chunking."""
    if not text:
        return []
    step = max(1, size - overlap)
    return [text[i: i + size] for i in range(0, len(text), step)]


@register(group="knowledge")
def index_document(path: str, chunk_size: int = 400, overlap: int = 80) -> dict:
    """Chunk a sandbox file or artifact and write each chunk into Memory as a searchable `fact`. Use this when the content must remain retrievable across later turns or runs (an indexing step before later vector queries). For one-shot inspection of a known file's contents in this turn, prefer `read_file` instead. Example: index_document("notes/spec.md")."""
    text, source = _read_for_index(path)
    if not text.strip():
        return {"path": path, "source": source, "chunks_indexed": 0, "warning": "empty content"}
    chunks = _chunk_text(text, size=chunk_size, overlap=overlap)
    run_id = f"index-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    indexed = 0
    for i, chunk in enumerate(chunks):
        preview = chunk[:120].replace("\n", " ")
        descriptor = f"[{source} chunk {i + 1}/{len(chunks)}] {preview}"
        _memory.add_fact(
            descriptor=descriptor,
            value={
                "chunk": chunk,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "source": source,
            },
            source=source,
            run_id=run_id,
        )
        indexed += 1
    return {
        "path": path,
        "source": source,
        "chunks_indexed": indexed,
        "chunk_size": chunk_size,
        "overlap": overlap,
    }


@register(group="knowledge")
def search_knowledge(query: str, k: int = 5) -> list[dict]:
    """Vector search over indexed `fact` chunks. Returns up to k ranked chunks with provenance. Call this rather than re-fetching URLs or re-reading source files whenever Memory already contains indexed chunks for the topic — that is the whole point of having indexed the corpus. Example: search_knowledge("authentication flow", 5)."""
    items = _memory.read(query, kinds=["fact"], top_k=k)
    return [
        {
            "id": item.id,
            "descriptor": item.descriptor,
            "source": item.source,
            "chunk": (item.value or {}).get("chunk") or "",
            "metadata": {k_: v for k_, v in (item.value or {}).items() if k_ != "chunk"},
        }
        for item in items
    ]
