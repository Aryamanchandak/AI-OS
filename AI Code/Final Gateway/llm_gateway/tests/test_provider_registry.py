from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))


def _reload(name: str):
    module = importlib.import_module(name)
    return importlib.reload(module)


def test_build_providers_vendor_toggles(monkeypatch):
    for key in (
        "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "ENABLE_GEMINI", "ENABLE_OPENAI", "ENABLE_ANTHROPIC",
        "ENABLE_OLLAMA_CHAT", "ENABLE_PHI4_CHAT",
    ):
        monkeypatch.delenv(key, raising=False)

    providers = _reload("providers")
    built = providers.build_providers(cache_store=None)
    assert list(built) == ["cover-vision-local"]
    assert built["cover-vision-local"].model == "gemma4:12b"
    assert built["cover-vision-local"].capabilities["images"] is True

    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("ENABLE_OPENAI", "0")
    providers = _reload("providers")
    built = providers.build_providers(cache_store=None)
    assert "gemma" not in built
    assert "gemini-cheap" in built
    assert "openai-cheap" not in built
    assert "anthropic-haiku" in built

    monkeypatch.setenv("ENABLE_OLLAMA_CHAT", "1")
    monkeypatch.setenv("ENABLE_PHI4_CHAT", "1")
    providers = _reload("providers")
    built = providers.build_providers(cache_store=None)
    assert "gemma" in built
    assert built["phi4-local"].model == "phi4:14b-q4_K_M"


@pytest_asyncio.fixture
async def client():
    import main as M

    transport = httpx.ASGITransport(app=M.app)
    async with M.app.router.lifespan_context(M.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
            yield c, M


@pytest.mark.asyncio
async def test_chat_does_not_failover_after_runtime_error(client, monkeypatch):
    c, M = client
    providers_mod = _reload("providers")
    router_mod = _reload("router")

    class FailingProvider:
        model = "broken-model"
        capabilities = {}

        def __init__(self):
            self.calls = 0

        async def chat(self, *args, **kwargs):
            self.calls += 1
            raise providers_mod.ProviderError("boom", status=500)

    class OkProvider:
        model = "ok-model"
        capabilities = {}

        def __init__(self):
            self.calls = 0

        async def chat(self, *args, **kwargs):
            self.calls += 1
            return {
                "text": "ok",
                "tool_calls": [],
                "input_tokens": 1,
                "output_tokens": 1,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "stop_reason": "end_turn",
                "model": self.model,
                "tool_call_dialect": "none",
                "reasoning_applied": False,
            }

    failing = FailingProvider()
    succeeding = OkProvider()
    monkeypatch.setattr(M.app.state, "providers", {
        "gemini-cheap": failing,
        "openai-cheap": succeeding,
    })
    monkeypatch.setattr(M.app.state, "router", router_mod.Router(M.app.state.providers, ["gemini-cheap", "openai-cheap"]))

    r = await c.post("/v1/chat", json={"prompt": "hello"})
    assert r.status_code == 502
    assert failing.calls == 1
    assert succeeding.calls == 0


@pytest.mark.asyncio
async def test_knowledge_extraction_profile_routes_to_sonnet(client, monkeypatch):
    c, M = client
    router_mod = _reload("router")

    class SonnetProvider:
        model = "claude-sonnet-4-6"
        capabilities = {"structured": True}

        def __init__(self):
            self.calls = 0

        async def chat(self, *args, **kwargs):
            self.calls += 1
            return {
                "text": "ok",
                "tool_calls": [],
                "input_tokens": 1,
                "output_tokens": 1,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "stop_reason": "end_turn",
                "model": self.model,
                "tool_call_dialect": "none",
                "reasoning_applied": False,
            }

    sonnet = SonnetProvider()
    providers = {"anthropic-sonnet": sonnet}
    monkeypatch.setattr(M.app.state, "providers", providers)
    monkeypatch.setattr(
        M.app.state,
        "router",
        router_mod.Router(providers, ["anthropic-sonnet"]),
    )

    response = await c.post(
        "/v1/chat",
        json={"prompt": "extract this", "profile": "knowledge-extraction-v1"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "anthropic-sonnet"
    assert response.json()["profile"] == "knowledge-extraction-v1"
    assert sonnet.calls == 1


@pytest.mark.asyncio
async def test_anthropic_profile_returns_gateway_validated_parsed_output(
    client, monkeypatch
):
    c, M = client
    router_mod = _reload("router")

    class StructuredSonnetProvider:
        model = "claude-sonnet-4-6"
        capabilities = {"structured": True}

        async def chat(self, *args, **kwargs):
            assert kwargs["response_format"].schema_["required"] == ["answer"]
            return {
                "text": '{"answer": 12}',
                "tool_calls": [],
                "input_tokens": 4,
                "output_tokens": 4,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "stop_reason": "end_turn",
                "model": self.model,
                "tool_call_dialect": "native",
                "reasoning_applied": False,
            }

    sonnet = StructuredSonnetProvider()
    providers = {"anthropic-sonnet": sonnet}
    monkeypatch.setattr(M.app.state, "providers", providers)
    monkeypatch.setattr(
        M.app.state,
        "router",
        router_mod.Router(providers, ["anthropic-sonnet"]),
    )

    response = await c.post(
        "/v1/chat",
        json={
            "prompt": "Return twelve.",
            "profile": "knowledge-extraction-v1",
            "response_format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "integer"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
                "name": "answer",
                "strict": True,
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["parsed"] == {"answer": 12}


@pytest.mark.asyncio
async def test_unknown_or_conflicting_chat_profile_is_rejected(client):
    c, _ = client

    unknown = await c.post(
        "/v1/chat",
        json={"prompt": "hello", "profile": "does-not-exist"},
    )
    conflicting = await c.post(
        "/v1/chat",
        json={
            "prompt": "hello",
            "profile": "knowledge-extraction-v1",
            "provider": "anthropic-sonnet",
        },
    )

    assert unknown.status_code == 400
    assert conflicting.status_code == 400


@pytest.mark.asyncio
async def test_document_segmentation_profile_is_exact_phi4_and_never_sonnet(
    client, monkeypatch
):
    c, M = client
    router_mod = _reload("router")

    class Provider:
        def __init__(self, model):
            self.model = model
            self.capabilities = {"structured": True}

    providers = {
        "phi4-local": Provider("phi4:14b-q4_K_M"),
        "anthropic-sonnet": Provider("claude-sonnet-4-6"),
    }
    monkeypatch.setattr(M.app.state, "providers", providers)
    monkeypatch.setattr(
        M.app.state,
        "router",
        router_mod.Router(providers, ["anthropic-sonnet"]),
    )

    response = await c.get("/v1/chat/profiles/document-segmentation-v1")

    assert response.status_code == 200
    assert response.json() == {
        "profile": "document-segmentation-v1",
        "provider": "phi4-local",
        "model": "phi4:14b-q4_K_M",
    }


@pytest.mark.asyncio
async def test_document_segmentation_profile_fails_when_phi4_is_disabled(
    client, monkeypatch
):
    c, M = client
    router_mod = _reload("router")
    providers = {}
    monkeypatch.setattr(M.app.state, "providers", providers)
    monkeypatch.setattr(M.app.state, "router", router_mod.Router(providers, []))

    response = await c.get("/v1/chat/profiles/document-segmentation-v1")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_cover_classification_profile_is_exact_local_vision_model(
    client, monkeypatch
):
    c, M = client
    router_mod = _reload("router")

    class Provider:
        model = "gemma4:12b"
        capabilities = {"images": True, "structured": True}

    local = Provider()
    providers = {
        "cover-vision-local": local,
        "anthropic-haiku": object(),
    }
    monkeypatch.setattr(M.app.state, "providers", providers)
    monkeypatch.setattr(
        M.app.state,
        "router",
        router_mod.Router(providers, ["anthropic-haiku"]),
    )

    response = await c.get("/v1/chat/profiles/cover-classification-v1")

    assert response.status_code == 200
    assert response.json() == {
        "profile": "cover-classification-v1",
        "provider": "cover-vision-local",
        "model": "gemma4:12b",
    }
    assert M.CHAT_PROFILES["cover-classification-v1"] not in M.DEFAULT_ORDER


@pytest.mark.asyncio
async def test_cover_classification_profile_fails_without_local_provider(
    client, monkeypatch
):
    c, M = client
    router_mod = _reload("router")
    providers = {"anthropic-haiku": object()}
    monkeypatch.setattr(M.app.state, "providers", providers)
    monkeypatch.setattr(
        M.app.state,
        "router",
        router_mod.Router(providers, ["anthropic-haiku"]),
    )

    response = await c.get("/v1/chat/profiles/cover-classification-v1")

    assert response.status_code == 503


def test_highlight_photo_profile_pins_to_anthropic_haiku():
    import main as M

    assert M.CHAT_PROFILES["highlight-photo-summary-v1"] == "anthropic-haiku"
