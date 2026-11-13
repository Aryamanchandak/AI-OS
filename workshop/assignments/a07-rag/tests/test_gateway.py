"""Offline tests for the small gateway: the wire translation and the ledger."""

from __future__ import annotations

import json

import httpx
import pytest

import gateway


def test_tools_and_schema_are_translated_to_the_wire_shape():
    body = gateway._request_body(
        "m", "hello", "be brief",
        tools=[{"name": "get_time", "description": "time", "input_schema": {"type": "object"}}],
        tool_choice="auto",
        response_format={"name": "Out", "schema": {"type": "object"}},
        temperature=0, max_tokens=10,
    )
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["tools"][0]["function"]["name"] == "get_time"
    assert body["tools"][0]["function"]["parameters"] == {"type": "object"}
    assert body["response_format"]["json_schema"]["name"] == "Out"


def test_a_tool_call_reply_comes_back_as_name_and_arguments():
    data = {"choices": [{"message": {"content": None, "tool_calls": [
        {"function": {"name": "get_time", "arguments": '{"timezone": "Asia/Tokyo"}'}}
    ]}}]}
    reply = gateway._parse_reply(data, wants_json=False)
    assert reply["tool_calls"] == [{"name": "get_time", "arguments": {"timezone": "Asia/Tokyo"}}]
    assert reply["text"] == ""


def test_a_json_reply_is_parsed():
    data = {"choices": [{"message": {"content": '{"goals": []}'}}]}
    assert gateway._parse_reply(data, wants_json=True)["parsed"] == {"goals": []}


def test_missing_key_fails_with_a_clear_message(monkeypatch):
    for var in ["LLM_API_KEY", *[v for v, _, _ in gateway._KNOWN_PROVIDERS]]:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="No model key found"):
        gateway._settings()


def test_every_call_is_logged_without_the_prompt_or_the_key(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "LEDGER_PATH", tmp_path / "llm_calls.jsonl")
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    def fake_post(url, json, headers, timeout):
        assert url == "https://example.test/v1/chat/completions"
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2},
        })

    monkeypatch.setattr(gateway.httpx, "post", fake_post)
    assert gateway.LLM().chat("a private prompt")["text"] == "hi"

    line = (tmp_path / "llm_calls.jsonl").read_text()
    row = json.loads(line)
    assert row["model"] == "test-model" and row["prompt_tokens"] == 7 and row["error"] is None
    assert "private prompt" not in line and "secret-key" not in line
