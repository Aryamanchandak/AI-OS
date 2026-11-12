"""Check real SDK request/response handling without paid or local model calls."""

import json

import anthropic
import httpx
import pytest
from openai import OpenAI

from simple_llm import LLM

SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"], "additionalProperties": False}


@pytest.mark.parametrize("provider", ["openai", "anthropic", "ollama"])
def test_chat_wire_format_and_structured_result(provider):
    bodies = []

    def handle(request):
        body = json.loads(request.content)
        bodies.append(body)
        if provider == "anthropic":
            assert request.headers["x-api-key"] == "test-key"
            response = {"id": "msg_1", "type": "message", "role": "assistant", "model": "test-model", "content": [{"type": "text", "text": '{"summary":"ok"}'}], "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}}
        else:
            assert request.headers["authorization"] == "Bearer test-key"
            response = {"id": "chat_1", "object": "chat.completion", "created": 1, "model": "test-model", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"summary":"ok"}'}}]}
        return httpx.Response(200, json=response)

    sdk_type = anthropic.Anthropic if provider == "anthropic" else OpenAI
    with LLM() as llm:
        llm._clients[provider] = sdk_type(api_key="test-key", http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        result = llm.chat("hello", system="extract", provider=provider, model="test-model", schema=SCHEMA)
    assert result["parsed"] == {"summary": "ok"}
    assert result["provider"] == provider
    if provider == "anthropic":
        assert bodies[0]["system"] == "extract"
        assert bodies[0]["output_config"]["format"]["schema"] == SCHEMA
    else:
        assert bodies[0]["messages"][0] == {"role": "system", "content": "extract"}
        assert bodies[0]["response_format"]["json_schema"]["schema"] == SCHEMA


def test_local_embedding():
    def handle(request):
        assert json.loads(request.content)["model"] == "nomic-embed-text"
        return httpx.Response(200, json={"object": "list", "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}], "model": "nomic-embed-text", "usage": {"prompt_tokens": 1, "total_tokens": 1}})

    with LLM() as llm:
        llm._clients["ollama"] = OpenAI(api_key="local", http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        result = llm.embed("hello")
    assert result["embedding"] == [0.1, 0.2]
    assert result["dim"] == 2


def test_missing_key_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with LLM(env_file=tmp_path / "absent.env") as llm:
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            llm.chat("hello", provider="openai")


def test_keys_load_from_explicit_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("ANTHROPIC_API_KEY=test-file-key\n")
    with LLM(env_file=path) as llm:
        assert llm._client("anthropic").api_key == "test-file-key"
    monkeypatch.delenv("ANTHROPIC_API_KEY")


def test_invalid_input_fails_before_calling():
    with LLM() as llm:
        with pytest.raises(ValueError, match="exactly one"):
            llm.chat()
