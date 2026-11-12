"""Phase 2 — parser in isolation (no brain, no server)."""

import pytest

from react_loop.parser import (
    Decision,
    MalformedDecision,
    UnknownTool,
    parse,
)

TOOLS = {"get_time", "currency_convert"}


def test_parses_tool_call():
    d = parse('{"thought": "check time", "tool": "get_time", "tool_input": {}}', TOOLS)
    assert d.tool == "get_time"
    assert d.tool_input == {}
    assert not d.is_final


def test_parses_final_answer():
    d = parse('{"thought": "done", "final_answer": "42"}', TOOLS)
    assert d.is_final
    assert d.final_answer == "42"


def test_strips_markdown_fences():
    d = parse('```json\n{"thought": "x", "tool": "get_time", "tool_input": {}}\n```', TOOLS)
    assert d.tool == "get_time"


def test_tolerates_surrounding_prose():
    text = 'Sure!\n{"thought": "x", "final_answer": "hi"}\nHope that helps.'
    d = parse(text, TOOLS)
    assert d.final_answer == "hi"


def test_malformed_json_raises_repairable():
    with pytest.raises(MalformedDecision):
        parse("this is not json at all", TOOLS)


def test_both_tool_and_final_rejected():
    with pytest.raises(MalformedDecision):
        parse('{"thought": "x", "tool": "get_time", "final_answer": "y"}', TOOLS)


def test_neither_tool_nor_final_rejected():
    with pytest.raises(MalformedDecision):
        parse('{"thought": "just thinking"}', TOOLS)


def test_unknown_tool_is_distinct_from_malformed():
    # Structurally valid, but names a tool that doesn't exist -> observation path.
    with pytest.raises(UnknownTool) as exc:
        parse('{"thought": "x", "tool": "nope", "tool_input": {}}', TOOLS)
    assert "nope" in str(exc.value)


def test_tool_input_defaults_to_empty():
    d = parse('{"thought": "x", "tool": "get_time"}', TOOLS)
    assert d.tool_input == {}
