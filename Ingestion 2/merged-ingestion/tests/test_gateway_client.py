"""The ingestion client must speak the AI OS gateway's address, paths and login."""

from __future__ import annotations

import json

import httpx
import pytest

from ingestion.gateway_client import LLM, GatewayError


def _client(handler, **kwargs) -> LLM:
    return LLM(token="test-token", transport=httpx.MockTransport(handler), **kwargs)


def test_chat_posts_to_gateway_with_token_and_returns_reply() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"text": "", "parsed": {"entities": []}})

    schema = {"type": "object", "properties": {"entities": {"type": "array"}}}
    reply = _client(handler).chat(
        "Extract entities",
        system="You extract.",
        profile="knowledge-extraction-v1",
        max_tokens=500,
        temperature=0.0,
        response_format={"type": "json_schema", "schema": schema},
    )

    assert seen["url"] == "http://127.0.0.1:8000/api/llm/chat"
    assert seen["auth"] == "Bearer test-token"
    # Unset fields are left out, so the gateway's own defaults apply.
    assert seen["body"] == {
        "prompt": "Extract entities",
        "system": "You extract.",
        "profile": "knowledge-extraction-v1",
        "max_tokens": 500,
        "temperature": 0.0,
        "response_format": {"type": "json_schema", "schema": schema},
    }
    assert reply["parsed"] == {"entities": []}


def test_embed_asks_for_the_pinned_embedding_profile() -> None:
    """Sending provider "ollama" makes the gateway use Ollama's chat model, so the client sends the profile."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"provider": "ollama", "model": "nomic-embed-text", "dim": 768, "embedding": [0.0] * 768},
        )

    reply = _client(handler).embed("a chunk", task_type="retrieval_document", provider="ollama")

    assert seen["url"] == "http://127.0.0.1:8000/api/llm/embed"
    assert seen["body"] == {"text": "a chunk", "task_type": "retrieval_document", "profile": "chunker-v1"}
    assert reply["dim"] == 768 and len(reply["embedding"]) == 768


def test_embed_refuses_any_provider_other_than_ollama() -> None:
    with pytest.raises(ValueError, match="ollama"):
        _client(lambda request: httpx.Response(200, json={})).embed("a chunk", provider="openai")


def test_resolve_chat_profile_reads_the_pinned_provider_and_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "http://127.0.0.1:8000/api/llm/chat/profiles/document-segmentation-v1"
        return httpx.Response(200, json={"provider": "phi4-local", "model": "phi4:14b-q4_K_M"})

    resolved = _client(handler).resolve_chat_profile("document-segmentation-v1")

    assert resolved == {"provider": "phi4-local", "model": "phi4:14b-q4_K_M"}


def test_gateway_error_carries_status_and_the_gateways_own_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "chat profile 'x' requires unavailable provider 'anthropic'"})

    with pytest.raises(GatewayError) as caught:
        _client(handler).chat("hi", profile="x")

    assert "503" in str(caught.value)
    assert "unavailable provider 'anthropic'" in str(caught.value)


def test_address_and_token_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_OS_GATEWAY_URL", "http://127.0.0.1:9999/")
    monkeypatch.setenv("AI_OS_TOKEN", "env-token")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={})

    LLM(transport=httpx.MockTransport(handler)).embed("x")

    assert seen["url"] == "http://127.0.0.1:9999/api/llm/embed"
    assert seen["auth"] == "Bearer env-token"


def test_missing_token_fails_before_any_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_OS_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="AI_OS_TOKEN"):
        LLM()
