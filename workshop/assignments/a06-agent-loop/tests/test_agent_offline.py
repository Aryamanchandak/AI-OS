"""Offline tests for the agent's contracts. No network, no model calls.

Each test states one rule from the assignment brief.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

import action
import agent6
import artifacts
import memory
from schemas import Block, Goal, GoalResult, ToolCall


@pytest.fixture
def clean_state(tmp_path, monkeypatch):
    """Point memory and artifacts at an empty folder."""
    monkeypatch.setattr(memory, "STATE_PATH", tmp_path / "memory.json")
    monkeypatch.setattr(memory, "_LOCK_PATH", tmp_path / "memory.lock")
    monkeypatch.setattr(artifacts, "STORE", tmp_path / "artifacts")
    monkeypatch.setattr(artifacts, "_LOCK_PATH", tmp_path / "artifacts" / ".lock")
    (tmp_path / "artifacts").mkdir()
    return tmp_path


class _NoCallSession:
    """An MCP session that fails the test if anything is dispatched."""

    async def call_tool(self, name, arguments):
        raise AssertionError(f"tool {name} must not be dispatched")


class _FakeResult:
    def __init__(self, text: str):
        self.structuredContent = None
        self.content = [type("Part", (), {"type": "text", "text": text})()]


class _BigResultSession:
    async def call_tool(self, name, arguments):
        return _FakeResult("x" * 10_000)


# ── Query C: durable memory across two runs ────────────────────────────────

def test_fact_from_run_one_is_found_in_run_two(clean_state, monkeypatch):
    monkeypatch.setattr(memory, "_llm_classify", lambda raw, schema: {"parsed": {
        "kind": "fact",
        "descriptor": "Mom's birthday is on 15 May 2026",
        "keywords": ["mom", "birthday", "may", "2026"],
        "value": {"person": "mom", "date": "2026-05-15"},
        "expires_at": None,
    }})
    memory.remember(
        "My mom's birthday is 15 May 2026. Remember that.",
        source="user_query", run_id="run1",
    )

    stored = json.loads((clean_state / "memory.json").read_text())
    assert stored[0]["kind"] == "fact"
    assert "birthday" in stored[0]["keywords"]

    hits = memory.read("When is mom's birthday?", kinds=["fact", "preference"])
    assert [h.descriptor for h in hits] == ["Mom's birthday is on 15 May 2026"]


def test_fact_is_still_saved_when_the_classifier_fails(clean_state, monkeypatch):
    def boom(raw, schema):
        raise RuntimeError("gateway down")

    monkeypatch.setattr(memory, "_llm_classify", boom)
    memory.remember("My mom's birthday is 15 May 2026.", source="user_query", run_id="run1")

    hits = memory.read("When is mom's birthday?", kinds=["fact"])
    assert len(hits) == 1
    assert "15 May 2026" in hits[0].descriptor


def test_clearing_state_forgets_everything(clean_state, monkeypatch):
    monkeypatch.setattr(memory, "_llm_classify", lambda raw, schema: {"parsed": {}})
    memory.remember("My mom's birthday is 15 May 2026.", source="user_query", run_id="run1")
    memory.clear()
    assert memory.read("When is mom's birthday?") == []


# ── Action: artifact handles are not paths ─────────────────────────────────

@pytest.mark.parametrize("arg", ["path", "url"])
def test_artifact_handle_is_refused_before_dispatch(arg):
    call = ToolCall(name="read_file", arguments={arg: "art:09ff0a67fe264eb9"})
    text, artifact_id = asyncio.run(action.execute(_NoCallSession(), call))
    assert text.startswith("ERROR")
    assert artifact_id is None


def test_large_tool_result_goes_to_the_artifact_store(clean_state):
    call = ToolCall(name="fetch_url", arguments={"url": "https://example.com"})
    text, artifact_id = asyncio.run(action.execute(_BigResultSession(), call))
    assert artifact_id is not None and artifact_id.startswith("art:")
    assert len(artifacts.get_bytes(artifact_id)) == 10_000
    assert len(text) < 1_000  # only a preview travels in the prompt


# ── Typed contracts between layers ─────────────────────────────────────────

def test_a_result_with_an_unknown_kind_is_rejected():
    with pytest.raises(ValidationError):
        GoalResult(goal_id="g1", kind="guess", output_descriptor="x", status="ok")


def test_a_tool_call_needs_structured_arguments():
    with pytest.raises(ValidationError):
        ToolCall(name="read_file", arguments="notes.txt")


# ── Final answer ───────────────────────────────────────────────────────────

def test_final_answer_follows_goal_order_and_reports_problems():
    block = Block(round=0, goals=[Goal(id="g1", text="first"), Goal(id="g2", text="second")])
    results = [
        GoalResult(goal_id="g2", kind="synthesis", output_descriptor="SECOND", status="ok"),
        GoalResult(goal_id="g1", kind="synthesis", output_descriptor="FIRST", status="ok"),
        GoalResult(goal_id="g3", kind="tool", output_descriptor="", status="error", message="timeout"),
    ]
    answer = agent6.compose_answer(results, [block])
    assert answer.index("FIRST") < answer.index("SECOND")
    assert "timeout" in answer
