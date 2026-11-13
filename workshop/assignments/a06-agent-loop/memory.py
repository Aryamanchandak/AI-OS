"""Memory: a typed service with four kinds, kept in one JSON file.

Everything lives in `state/memory.json`, so facts and preferences survive
between runs and deleting `state/` resets the agent. Reads rank items by
keyword overlap with the query and the recent history. Items past their
`expires_at` are never returned.

Free-form content (the user's query) is classified by one gateway call
into a kind, a descriptor and keywords. Tool outcomes are written without
a model call because their kind is already known.
"""

from __future__ import annotations

import fcntl
import json
import logging
import re
import threading
from datetime import datetime

log = logging.getLogger(__name__)

from pydantic import BaseModel, Field

from paths import STATE_DIR
from gateway import LLM
from schemas import MemoryItem, ToolCall, new_id
import artifacts

STATE_PATH = STATE_DIR / "memory.json"
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

_LOCK_PATH = STATE_PATH.with_suffix(".lock")
_thread_lock = threading.Lock()


def _is_expired(item: MemoryItem) -> bool:
    """Hard-expiry check: items past `expires_at` are dropped from read
    results. `expires_at is None` (the default) means durable — never
    expires."""
    return item.expires_at is not None and item.expires_at < datetime.utcnow()


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


# ── keyword search ──────────────────────────────────────────────────────────

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
        if _is_expired(item):
            continue
        itoks = {w.lower() for w in item.keywords} | _tokens(item.descriptor)
        score = len(qtoks & itoks)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    return [i for _, i in scored[:top_k]]


def read(
    query: str,
    history: list[dict] | None = None,
    *,
    kinds: list[str] | None = None,
    top_k: int = 8,
) -> list[MemoryItem]:
    """Items whose keywords or descriptor overlap the query, best first."""
    hits = _keyword_search(query, history, kinds=kinds, top_k=top_k)
    print(f"[memory]        {len(hits)} keyword hits")
    return hits


# ── writes ──────────────────────────────────────────────────────────────────

class _Classification(BaseModel):
    """What the LLM classifier returns for an ambiguous free-form write."""

    kind: str
    descriptor: str
    keywords: list[str] = Field(default_factory=list)
    value: dict = Field(default_factory=dict)
    expires_at: str | None = None


def _persist_item(item: MemoryItem) -> MemoryItem:
    """Append `item` to the JSON store. Returns it for caller convenience."""
    with _thread_lock:  # in-process
        with open(_LOCK_PATH, "w") as _lf:
            fcntl.flock(_lf, fcntl.LOCK_EX)  # across processes
            items = _load()
            items.append(item)
            _save(items)
            fcntl.flock(_lf, fcntl.LOCK_UN)
    return item


def _parse_expires_at(raw: str | None) -> "datetime | None":
    """Parse the classifier's `expires_at` (an ISO date/datetime string) into
    a datetime. Unparseable or absent -> None (durable), never a crash."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        log.warning("[memory.remember] unparseable expires_at %r; treating as durable", raw)
        return None


def _fallback_remember(
    raw_text: str, *, source: str, run_id: str, goal_id: str | None,
) -> MemoryItem:
    """Deterministic write when the classifier LLM is unavailable.
    Keyword extraction is naive (top word tokens); kind defaults to fact."""
    toks = list(_tokens(raw_text))[:10]
    descriptor = raw_text[:200]
    item = MemoryItem(
        id=new_id("mem"),
        kind="fact",
        keywords=toks,
        descriptor=descriptor,
        value={"raw": raw_text},
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
    """LLM-classified write for ambiguous content (user input, free-form
    observation). One classifier call. If the
    classifier fails, the deterministic fallback handles the write."""
    schema = _Classification.model_json_schema()
    try:
        reply = _llm_classify(raw_text, schema)
    except Exception as e:
        log.warning("[memory.remember] classifier failed (%r); falling back to fact-write", e)
        return _fallback_remember(raw_text, source=source, run_id=run_id, goal_id=goal_id)

    parsed = reply.get("parsed") or {}
    # Keep the fallback even with deterministic classification: the raw text
    # should never disappear if the model returns an empty structured value.
    parsed_value = parsed.get("value")
    if not parsed_value:
        parsed_value = {"raw": raw_text}
    c = _Classification.model_validate({
        "kind": parsed.get("kind", "fact"),
        "descriptor": parsed.get("descriptor", raw_text[:120]),
        "keywords": parsed.get("keywords") or list(_tokens(raw_text))[:10],
        "value": parsed_value,
        "expires_at": parsed.get("expires_at"),
    })

    item = MemoryItem(
        id=new_id("mem"),
        kind=c.kind,  # type: ignore[arg-type]
        keywords=[k.lower() for k in c.keywords],
        descriptor=c.descriptor,
        value=c.value,
        source=source,
        run_id=run_id,
        goal_id=goal_id,
        expires_at=_parse_expires_at(c.expires_at),
    )
    return _persist_item(item)


def _llm_classify(raw_text: str, schema: dict) -> dict:
    return LLM().chat(
        prompt=(
            "Classify the following content into a JSON memory record.\n\n"
            f"CONTENT: {raw_text!r}\n\n"
            "Return a JSON object with these fields:\n"
            "- kind ∈ {fact, preference, tool_outcome, scratchpad}.\n"
            "- descriptor: one short human-readable line. MUST include any\n"
            "  specific dates (e.g. '15 May 2026'), numbers, names, places,\n"
            "  or other concrete entities present in the content — these are\n"
            "  what later retrieval will key off. 'Mom's birthday is on 15\n"
            "  May 2026' is a good descriptor; 'birthday and reminder\n"
            "  schedule' is a bad descriptor.\n"
            "- keywords: 3-8 lowercase search keywords pulled from the content.\n"
            "- value: a dict with structured fields (entities, dates,\n"
            "  attributes). MUST NOT be empty when the content has any\n"
            "  identifiable entity — if you cannot classify a specific\n"
            "  attribute, include {\"raw\": <the original content>}.\n"
            "- expires_at: an ISO date (YYYY-MM-DD) after which this content\n"
            "  is no longer useful, or null if it's durable. Set this when\n"
            "  the content is tied to a specific dated event or deadline\n"
            "  (an exam, a submission, a meeting, a trip) — this system exists\n"
            "  to help BEFORE that date, so pick the date itself (or the day\n"
            "  after) as the expiry. Leave null for identity/relationship facts\n"
            "  that recur or never expire (birthdays, names, relationships) and\n"
            "  for open-ended preferences."
        ),
        response_format={
            "type": "json_schema",
            "schema": schema,
            "name": "Classification",
            "strict": True,
        },
        temperature=0,
    )


def record_outcome(
    *,
    tool_call: ToolCall,
    result_text: str,
    artifact_id: str | None,
    run_id: str,
    goal_id: str | None,
) -> MemoryItem:
    """Zero-LLM-classify write for a deterministic tool outcome. Kind is
    `tool_outcome` by construction."""
    arg_words = []
    for v in tool_call.arguments.values():
        if isinstance(v, str):
            arg_words += _tokens(v)
        elif isinstance(v, (int, float)):
            arg_words.append(str(v))
    keywords = list({tool_call.name.lower(), *arg_words})[:10]

    preview = result_text[:200].replace("\n", " ")
    descriptor = f"{tool_call.name}({json.dumps(tool_call.arguments)[:80]}) -> {preview}"
    if artifact_id:
        descriptor += f" [artifact {artifact_id}]"


    item = MemoryItem(
        id=new_id("mem"),
        kind="tool_outcome",
        keywords=keywords,
        descriptor=descriptor,
        value={
            "tool": tool_call.name,
            "arguments": tool_call.arguments,
            "raw": result_text if artifact_id is None else result_text[:400],
        },
        artifact_id=artifact_id,
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
    classifier because the kind is known."""
    item = MemoryItem(
        id=new_id("mem"),
        kind="fact",
        keywords=list({k.lower() for k in (keywords or list(_tokens(descriptor))[:10])}),
        descriptor=descriptor,
        value=value or {},
        source=source,
        run_id=run_id,
        goal_id=goal_id,
    )
    return _persist_item(item)


def clear() -> None:
    """Wipe persistent memory and artifacts."""
    with _thread_lock:
        with open(_LOCK_PATH, "w") as _lf:
            fcntl.flock(_lf, fcntl.LOCK_EX)
            if STATE_PATH.exists():
                STATE_PATH.unlink()
            artifacts.clear()
            fcntl.flock(_lf, fcntl.LOCK_UN)


def gc_artifacts(*, dry_run: bool = True) -> list[str]:
    """Delete artifacts not referenced by any memory item.

    Returns the artifact ids that would be or were deleted.
    """
    referenced = {
        item.artifact_id for item in _load()
        if item.artifact_id is not None
    }
    return artifacts.gc(referenced, dry_run=dry_run)
