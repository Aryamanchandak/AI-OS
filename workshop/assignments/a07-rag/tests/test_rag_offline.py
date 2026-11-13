"""Offline tests for vector memory and document indexing.

The embedding model is replaced by a tiny stand-in that maps words to a few
"meaning" axes, so related words land close together without any network
call. That is enough to test the plumbing: what gets indexed, what comes
back, and what survives a restart.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

import artifacts
import mcp_server
import memory
import perception
from vector_index import VectorIndex

MEANINGS = [
    {"credit", "assignment", "blame", "gradient", "gradients", "backpropagation", "reward"},
    {"birthday", "mom", "born", "mother"},
    {"bond", "bonds", "yield", "yields", "duration", "coupon"},
    {"transformer", "attention", "encoder", "decoder"},
]


def fake_embed(text: str, task_type: str = "retrieval_document") -> list[float]:
    words = set(memory.re.findall(r"\w+", text.lower()))
    vec = [float(len(words & axis)) for axis in MEANINGS]
    return vec + [0.01]  # never a zero vector


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "STATE_PATH", tmp_path / "memory.json")
    monkeypatch.setattr(memory, "_LOCK_PATH", tmp_path / "memory.lock")
    monkeypatch.setattr(artifacts, "STORE", tmp_path / "artifacts")
    monkeypatch.setattr(artifacts, "_LOCK_PATH", tmp_path / "artifacts" / ".lock")
    (tmp_path / "artifacts").mkdir()
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setattr(mcp_server, "SANDBOX", sandbox)
    monkeypatch.setattr(memory, "_try_embed", fake_embed)
    return tmp_path


def _fact(text: str, source: str = "test") -> None:
    memory.add_fact(text, value={"chunk": text}, source=source, run_id="r1")


# ── retrieval ──────────────────────────────────────────────────────────────

def test_a_related_fact_is_found_even_with_no_shared_words(state):
    _fact("Backpropagation sends gradients to earlier layers.")
    _fact("A bond's coupon is fixed at issue.")

    query = "How is blame shared out?"
    assert memory._keyword_search(query, None, kinds=["fact"], top_k=5) == []

    hits = memory.read(query, kinds=["fact"], top_k=1)
    assert hits[0].descriptor.startswith("Backpropagation")


def test_keyword_search_still_works_when_embeddings_are_down(state, monkeypatch):
    monkeypatch.setattr(memory, "_try_embed", lambda text, task_type: None)
    _fact("Mom's birthday is on 15 May 2026")
    hits = memory.read("When is mom's birthday?", kinds=["fact"])
    assert len(hits) == 1


def test_only_the_requested_kinds_come_back(state):
    _fact("A bond's yield moves against its price.")
    memory.record_outcome(
        tool_call=memory.ToolCall(name="web_search", arguments={"query": "bond yield"}),
        result_text="bond yield results", artifact_id=None, run_id="r1", goal_id=None,
    )
    hits = memory.read("bond yield", kinds=["fact"])
    assert {h.kind for h in hits} == {"fact"}


def test_an_expired_fact_is_never_returned(state):
    _fact("A bond's yield moves against its price.")
    items = memory._load()
    items[0].expires_at = datetime.utcnow() - timedelta(days=1)
    memory._save(items)
    assert memory.read("bond yield", kinds=["fact"]) == []


# ── persistence ────────────────────────────────────────────────────────────

def test_the_index_on_disk_matches_memory_after_a_restart(state):
    _fact("Backpropagation sends gradients to earlier layers.")
    _fact("A bond's coupon is fixed at issue.")

    reopened = VectorIndex(state)  # what a fresh process would load
    stored_ids = [i["id"] for i in json.loads((state / "memory.json").read_text())]
    assert reopened.ids == stored_ids
    assert reopened.size == 2


def test_a_lost_index_file_is_rebuilt_from_memory(state):
    _fact("Backpropagation sends gradients to earlier layers.")
    (state / "index.faiss").unlink()
    (state / "index_ids.json").unlink()

    hits = memory.read("gradient blame", kinds=["fact"], top_k=1)
    assert hits[0].descriptor.startswith("Backpropagation")
    assert (state / "index.faiss").exists()


def test_vectors_of_a_different_size_are_refused(state):
    index = VectorIndex(state)
    index.add("a", [1.0, 0.0, 0.0])
    with pytest.raises(ValueError, match="does not match index dim"):
        index.add("b", [1.0, 0.0])


# ── chunking and the two index tools ───────────────────────────────────────

def test_chunks_overlap_and_cover_the_whole_text():
    words = [f"w{i}" for i in range(1000)]
    chunks = mcp_server._chunk_text(" ".join(words), size=400, overlap=80)
    assert [len(c.split()) for c in chunks] == [400, 400, 360]
    assert chunks[0].split()[-80:] == chunks[1].split()[:80]
    assert chunks[-1].split()[-1] == "w999"


def test_empty_text_makes_no_chunks():
    assert mcp_server._chunk_text("   ") == []


def test_indexing_a_file_stores_every_chunk_with_its_source(state):
    (state / "sandbox" / "notes.md").write_text(" ".join(["bond"] * 500))
    report = mcp_server.index_document("notes.md", chunk_size=400, overlap=80)
    assert report["chunks_indexed"] == 2

    facts = [i for i in memory._load() if i.kind == "fact"]
    assert len(facts) == 2
    assert all(f.source == "sandbox:notes.md" for f in facts)
    assert [f.value["chunk_index"] for f in facts] == [0, 1]


def test_search_returns_the_chunk_text_and_where_it_came_from(state):
    (state / "sandbox" / "a.md").write_text("Backpropagation sends gradients to earlier layers.")
    (state / "sandbox" / "b.md").write_text("A bond coupon is fixed at issue.")
    mcp_server.index_document("a.md")
    mcp_server.index_document("b.md")

    top = mcp_server.search_knowledge("who gets the blame", k=1)[0]
    assert top["source"] == "sandbox:a.md"
    assert "Backpropagation" in top["chunk"]


def test_a_file_outside_the_sandbox_cannot_be_indexed(state):
    with pytest.raises(Exception):
        mcp_server.index_document("../memory.json")


# ── the architecture gate from the brief ───────────────────────────────────

TOOL_NAMES = [
    "web_search", "fetch_url", "get_time", "currency_convert", "read_file", "list_dir",
    "create_file", "update_file", "edit_file", "index_document", "search_knowledge",
]


@pytest.mark.parametrize("tool", TOOL_NAMES)
def test_perception_never_names_a_tool(tool):
    assert tool not in perception.PLAN_SYSTEM
    assert tool not in perception.REVIEW_SYSTEM
