from types import SimpleNamespace

import pytest

from agent.llm import AnthropicLLM, build_llm


class Messages:
    def __init__(self, stop="end_turn", text="answer"):
        self.stop, self.text, self.payload = stop, text, None

    def create(self, **payload):
        self.payload = payload
        return SimpleNamespace(stop_reason=self.stop,
                               content=[SimpleNamespace(type="text", text=self.text)],
                               usage=SimpleNamespace(input_tokens=12, output_tokens=4))


def test_direct_provider_contract_and_usage():
    messages = Messages()
    client = AnthropicLLM(client=SimpleNamespace(messages=messages), model="fixture-model")
    assert client.complete("system", "user") == "answer"
    assert messages.payload["model"] == "fixture-model"
    assert messages.payload["messages"] == [{"role":"user", "content":"user"}]
    assert client.usage == {"calls":1,"input_tokens":12,"output_tokens":4}


def test_truncated_output_fails():
    client = AnthropicLLM(client=SimpleNamespace(messages=Messages("max_tokens")))
    with pytest.raises(RuntimeError, match="truncated"):
        client.complete("system", "user")


def test_no_gateway_token_or_service_is_required(monkeypatch):
    monkeypatch.delenv("AI_OS_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-fixture-only")
    monkeypatch.setenv("ANTHROPIC_MODEL", "custom-model")
    captured = {}
    def factory(**kwargs):
        captured.update(kwargs)
        return "direct-client"
    monkeypatch.setattr("agent.llm.AnthropicLLM", factory)
    assert build_llm({}) == "direct-client"
    assert captured["api_key"] == "test-fixture-only"
    assert captured["model"] == "custom-model"


def test_missing_key_has_actionable_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        build_llm({})
