"""Phase 3 — the whole loop, end to end, against the stub MCP server.

Uses FakeBrain (scripted decisions) so no OpenAI key is needed. This is exactly
the "test in isolation with fake tool results" the plan calls for, extended to
drive the real MCPClient + parser + guards + trace + controller together. It
proves the *mechanics*; the live OpenAI run is a separate, key-gated concern.
"""

import os
import sys

import pytest

from react_loop.brain import FakeBrain
from react_loop.config import LoopConfig, ServerConfig
from react_loop.loop import ReactLoop
from react_loop.mcp_client import MCPClient

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STUB = os.path.join(_REPO, "tests", "stub_server.py")


def _stub_server() -> ServerConfig:
    # Launch the stub in THIS interpreter's environment (it has `mcp`).
    return ServerConfig(command=sys.executable, args=[_STUB], cwd=_REPO)


def _cfg(brain_replies=None, **over) -> LoopConfig:
    base = dict(
        model="fake",
        api_key="unused",
        max_iterations=over.pop("max_iterations", 8),
        max_repairs=over.pop("max_repairs", 3),
        observation_char_limit=over.pop("observation_char_limit", 4000),
        server=_stub_server(),
    )
    base.update(over)
    return LoopConfig(**base)


async def _run(replies, task="test task", **over):
    cfg = _cfg(**over)
    brain = FakeBrain(replies)
    async with MCPClient(cfg.server) as client:
        loop = ReactLoop(brain, client, cfg)
        return await loop.run(task)


async def test_happy_path_chains_two_tools():
    result = await _run([
        '{"thought": "get the time", "tool": "get_time", "tool_input": {}}',
        '{"thought": "convert", "tool": "currency_convert", "tool_input": {"amount": 100, "from_currency": "USD", "to_currency": "EUR"}}',
        '{"thought": "done", "final_answer": "It is noon UTC; 100 USD = 90 EUR."}',
    ])
    assert result.stop_reason == "final_answer"
    assert "90 EUR" in result.final_answer
    kinds = [e.kind for e in result.trajectory.entries]
    assert kinds == ["action", "action", "final"]
    # Observation from the real stub tool actually landed in the trace.
    assert "2026-07-04T12:00:00Z" in result.trajectory.entries[0].observation


async def test_repair_path_recovers_from_malformed_json():
    result = await _run([
        "I think I should get the time.",              # malformed -> repair
        '{"thought": "ok now valid", "final_answer": "recovered"}',
    ])
    assert result.stop_reason == "final_answer"
    assert result.final_answer == "recovered"
    assert any(e.kind == "repair" for e in result.trajectory.entries)


async def test_repair_exhaustion_stops_cleanly():
    result = await _run(
        ["nonsense"] * 10,          # never valid
        max_repairs=2,
    )
    assert result.stop_reason == "repair_exhausted"
    assert result.final_answer is None


async def test_unknown_tool_becomes_observation_then_recovers():
    result = await _run([
        '{"thought": "guess a tool", "tool": "make_coffee", "tool_input": {}}',
        '{"thought": "use a real one", "tool": "get_time", "tool_input": {}}',
        '{"thought": "done", "final_answer": "ok"}',
    ])
    assert result.stop_reason == "final_answer"
    # The unknown-tool step is recorded as an action carrying the error obs.
    first = result.trajectory.entries[0]
    assert first.tool == "make_coffee"
    assert "Unknown tool" in first.observation


async def test_repeat_guard_intervenes():
    result = await _run([
        '{"thought": "t", "tool": "get_time", "tool_input": {}}',
        '{"thought": "again identical", "tool": "get_time", "tool_input": {}}',
        '{"thought": "done", "final_answer": "ok"}',
    ])
    assert any(e.kind == "guard" for e in result.trajectory.entries)
    assert result.stop_reason == "final_answer"


async def test_tool_error_is_an_observation_not_a_crash():
    result = await _run([
        '{"thought": "try failing tool", "tool": "always_fails", "tool_input": {}}',
        '{"thought": "give up gracefully", "final_answer": "handled the error"}',
    ])
    assert result.stop_reason == "final_answer"
    obs = result.trajectory.entries[0].observation
    assert "ERROR" in obs


async def test_max_iterations_cap():
    # Brain never finalizes; loop must stop at the cap.
    tool_call = '{"thought": "loop", "tool": "get_time", "tool_input": {"n": %d}}'
    result = await _run(
        [tool_call % i for i in range(20)],   # distinct args dodge repeat-guard
        max_iterations=3,
    )
    assert result.stop_reason == "max_iterations"
    assert result.final_answer is None
    assert sum(1 for e in result.trajectory.entries if e.kind == "action") == 3


async def test_vague_prompt_with_no_target_asks_before_tools():
    class NoToolsClient:
        async def list_tools(self):  # pragma: no cover - must not be called
            raise AssertionError("list_tools should not be called for vague prompt")

    cfg = _cfg()
    brain = FakeBrain([])
    loop = ReactLoop(brain, NoToolsClient(), cfg)

    result = await loop.run("Can you make this better?")

    assert result.stop_reason == "final_answer"
    assert result.final_answer == (
        "Please paste the content or identify the file you would like me to improve."
    )
    assert len(brain.calls) == 0
    assert [e.kind for e in result.trajectory.entries] == ["final"]


async def test_vague_prompt_with_named_file_continues_to_tools():
    result = await _run(
        [
            '{"thought": "named file is grounded", "final_answer": "would read report.txt"}',
        ],
        task="Improve report.txt",
    )

    assert result.stop_reason == "final_answer"
    assert result.final_answer == "would read report.txt"


async def test_recovery_retry_changes_arguments_before_success():
    result = await _run([
        '{"thought": "first bad call", "tool": "echo", "tool_input": {"text": "bad"}}',
        '{"thought": "retry with corrected input", "tool": "echo", "tool_input": {"text": "good"}}',
        '{"thought": "success observed", "final_answer": "The corrected call succeeded."}',
    ])
    actions = [e for e in result.trajectory.entries if e.kind == "action"]

    assert result.stop_reason == "final_answer"
    assert len(actions) == 2
    assert actions[0].tool_input != actions[1].tool_input
    assert result.trajectory.entries[-1].final_answer == "The corrected call succeeded."
