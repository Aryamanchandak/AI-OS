"""Memory: a typed service with four kinds.

Session 7 adds vector retrieval on top of the Session 6 service. Reads go
through FAISS first (cosine similarity over the `embedding` field). When
the vector path returns nothing, the read falls back to the S6 keyword
overlap. Writes embed the descriptor at insert time for items of kind
`fact`, `preference`, and `tool_outcome`. Scratchpad items skip embedding.

The classifying write for ambiguous free-form content still uses one
gateway chat call (provider="flash"). The embedding call is a
separate gateway endpoint, `POST /v1/embed`, exposed by `gateway.embed()`.

Three honest design choices flagged in the Session 7 notes:
  1. Vector retrieval only. Hybrid retrieval with RRF arrives in a future
     session.
  2. Sliding-window chunking inside `index_document` is heuristic.
     Semantic chunking arrives in Session 8.
  3. The embedding model is fixed at the gateway level. Switching it
     invalidates every FAISS index already built. Treat the model as a
     project-level constant.
"""

from __future__ import annotations

import fcntl
import json
import logging
import re
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)


from gateway import embed as _gateway_embed
from schemas import MemoryItem, ToolCall, new_id
from vector_index import VectorIndex

STATE_PATH = Path(__file__).parent / "state" / "memory.json"
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

_LOCK_PATH = STATE_PATH.with_suffix(".lock")
_thread_lock = threading.Lock()

# Kinds for which an embedding is computed at write time. Scratchpad items
# are run-scoped and skip the vector path.
_EMBEDDABLE_KINDS = {"fact", "preference", "tool_outcome"}


# ── persistence ─────────────────────────────────────────────────────────────

def _load() -> list[MemoryItem]:
    if not STATE_PATH.exists():
        return []
    raw = json.loads(STATE_PATH.read_text())
    return [MemoryItem.model_validate(r) for r in raw]


def _save(items: list[MemoryItem]) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps([i.model_dump(mode="json") for i in items], indent=2))
    tmp.replace(STATE_PATH)  # atomic rename; prevents partial-read JSONDecodeErrors


# ── vector index ────────────────────────────────────────────────────────────

def _index() -> VectorIndex:
    """Return a freshly-loaded FAISS index every call.

    Re-reading the index file is cheap at S7 scale and keeps the agent
    process consistent with writes made by the MCP subprocess (which runs
    `index_document` in a separate Python process and persists to the same
    disk files). On cold start (no index files on disk), the index is
    rebuilt from items already persisted in `memory.json`.
    """
    idx = VectorIndex(STATE_PATH.parent)
    if idx.size == 0:
        for item in _load():
            if item.embedding is not None:
                idx.add(item.id, item.embedding)
        if idx.size > 0:
            idx.persist()
    return idx


def _try_embed(text: str, task_type: str) -> list[float]:
    t0 = time.perf_counter()
    resp = _gateway_embed(text, task_type=task_type)
    vec = list(resp["embedding"])
    ms = (time.perf_counter() - t0) * 1000
    print(f"[embed]         {task_type} ({len(text)} chars) → {len(vec)}d  {ms:.0f}ms")
    return vec


# ── keyword search (Session 6 path, used as fallback) ───────────────────────

_STOPWORDS = {
    "the", "is", "a", "an", "of", "to", "and", "or", "in", "on", "for", "at",
    "with", "by", "from", "what", "how", "when", "where", "why", "this", "that",
    "it", "be", "as", "are", "was", "were", "i", "you", "me", "my", "your",
}


def _tokens(text: str) -> set[str]:
    return {
        w for w in re.findall(r"\w+", text.lower())
        if w not in _STOPWORDS and len(w) > 2
    }


def _keyword_search(
    query: str,
    history: list[dict] | None,
    *,
    kinds: list[str] | None,
    top_k: int,
) -> list[MemoryItem]:
    items = _load()
    if kinds:
        items = [i for i in items if i.kind in kinds]
    qtoks = _tokens(query)
    if history:
        for h in history[-3:]:
            qtoks |= _tokens(json.dumps(h, default=str))
    scored: list[tuple[int, MemoryItem]] = []
    for item in items:
        itoks = {w.lower() for w in item.keywords} | _tokens(item.descriptor)
        score = len(qtoks & itoks)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    return [i for _, i in scored[:top_k]]


# ── vector search (the new S7 path) ─────────────────────────────────────────

def _vector_search(
    query: str,
    *,
    kinds: list[str] | None,
    top_k: int,
    query_vec: list[float] | None = None,
) -> list[MemoryItem]:
    qvec = query_vec or _try_embed(query, task_type="retrieval_query")
    idx = _index()
    if idx.size == 0:
        print(f"[memory]        vector index is empty — skipping vector search")
        return []
    hits = idx.search(qvec, k=top_k * 2 if kinds else top_k)
    if not hits:
        return []
    by_id: dict[str, MemoryItem] = {item.id: item for item in _load()}
    out: list[MemoryItem] = []
    for item_id, _score in hits:
        item = by_id.get(item_id)
        if item is None:
            continue
        if kinds and item.kind not in kinds:
            continue
        out.append(item)
        if len(out) >= top_k:
            break
    return out


def read(
    query: str,
    history: list[dict] | None = None,
    *,
    kinds: list[str] | None = None,
    top_k: int = 8,
    query_vec: list[float] | None = None,
) -> list[MemoryItem]:
    """Vector first, keyword as fallback when vector returns nothing."""
    vec_hits = _vector_search(query, kinds=kinds, top_k=top_k, query_vec=query_vec)
    if vec_hits:
        print(f"[memory]        vector path → {len(vec_hits)} hits")
        return vec_hits
    kw_hits = _keyword_search(query, history, kinds=kinds, top_k=top_k)
    if kw_hits:
        print(f"[memory]        keyword fallback → {len(kw_hits)} hits (vector returned 0)")
    else:
        print(f"[memory]        no hits on vector or keyword path")
    return kw_hits


# ── writes ──────────────────────────────────────────────────────────────────


def _persist_item(item: MemoryItem) -> MemoryItem:
    """Append `item` to the JSON store and, if it has an embedding, to the
    FAISS index. Returns the same item for caller convenience."""
    with _thread_lock:  # in-process serialization (multiple FastAPI threads)
        with open(_LOCK_PATH, "w") as _lf:
            fcntl.flock(_lf, fcntl.LOCK_EX)  # cross-process (MCP subprocess)
            items = _load()
            items.append(item)
            _save(items)
            fcntl.flock(_lf, fcntl.LOCK_UN)
    if item.embedding is not None and item.kind in _EMBEDDABLE_KINDS:
        idx = _index()
        idx.add(item.id, item.embedding)
        idx.persist()
    return item


def _fallback_remember(
    raw_text: str, *, source: str, run_id: str, goal_id: str | None,
) -> MemoryItem:
    """Deterministic write when the classifier LLM is unavailable.
    Keyword extraction is naive (top word tokens); kind defaults to fact.
    The embedding is still attempted; if it fails the item persists without
    a vector and stays reachable through the keyword fallback."""
    toks = list(_tokens(raw_text))[:10]
    descriptor = raw_text[:200]
    embedding = _try_embed(descriptor, task_type="retrieval_document")
    item = MemoryItem(
        id=new_id("mem"),
        kind="fact",
        keywords=toks,
        descriptor=descriptor,
        value={"raw": raw_text},
        embedding=embedding,
        source=source,
        run_id=run_id,
        goal_id=goal_id,
    )
    return _persist_item(item)


def remember(
    raw_text: str,
    *,
    source: str,
    run_id: str,
    goal_id: str | None = None,
) -> MemoryItem:
    """Deterministic fact write for user input and free-form observations."""
    return _fallback_remember(raw_text, source=source, run_id=run_id, goal_id=goal_id)


def record_outcome(
    *,
    tool_call: ToolCall,
    result_text: str,
    artifact_id: str | None,
    run_id: str,
    goal_id: str | None,
) -> MemoryItem:
    """Zero-LLM-classify write for a deterministic tool outcome. Kind is
    `tool_outcome` by construction. Embedding is computed from the
    descriptor so the outcome remains retrievable by semantic similarity."""
    arg_words = []
    for v in tool_call.arguments.values():
        if isinstance(v, str):
            arg_words += _tokens(v)
        elif isinstance(v, (int, float)):
            arg_words.append(str(v))
    keywords = list({tool_call.name.lower(), *arg_words})[:10]

    descriptor = f"{tool_call.name}({json.dumps(tool_call.arguments)[:80]}) -> "
    if artifact_id:
        descriptor += f"artifact {artifact_id}"
    else:
        descriptor += result_text[:120].replace("\n", " ")

    embedding = _try_embed(descriptor, task_type="retrieval_document")

    item = MemoryItem(
        id=new_id("mem"),
        kind="tool_outcome",
        keywords=keywords,
        descriptor=descriptor,
        value={
            "tool": tool_call.name,
            "arguments": tool_call.arguments,
            "result_preview": result_text[:400],
        },
        artifact_id=artifact_id,
        embedding=embedding,
        source="action",
        run_id=run_id,
        goal_id=goal_id,
    )
    return _persist_item(item)


def add_fact(
    descriptor: str,
    *,
    value: dict | None = None,
    keywords: list[str] | None = None,
    source: str,
    run_id: str,
    goal_id: str | None = None,
) -> MemoryItem:
    """Direct fact write used by document-indexing tools. Skips the LLM
    classifier (kind is known) but still embeds the descriptor."""
    embedding = _try_embed(descriptor, task_type="retrieval_document")
    item = MemoryItem(
        id=new_id("mem"),
        kind="fact",
        keywords=list({k.lower() for k in (keywords or list(_tokens(descriptor))[:10])}),
        descriptor=descriptor,
        value=value or {},
        embedding=embedding,
        source=source,
        run_id=run_id,
        goal_id=goal_id,
    )
    return _persist_item(item)


def clear() -> None:
    """Wipe persistent memory and the vector index. Useful between
    assignment attempts."""
    with _thread_lock:
        with open(_LOCK_PATH, "w") as _lf:
            fcntl.flock(_lf, fcntl.LOCK_EX)
            if STATE_PATH.exists():
                STATE_PATH.unlink()
            fcntl.flock(_lf, fcntl.LOCK_UN)
    VectorIndex(STATE_PATH.parent).clear()
