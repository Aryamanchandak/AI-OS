"""The ingestion client reaches Gateway's real LLM HTTP routes."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gateway.app.dependencies import get_llm_service
from gateway.app.main import create_app
from gateway.ingestion.http_client import GatewayHTTPClient, GatewayHTTPError
from gateway.ingestion.vector.vector_store import EMBEDDING_DIMENSION, validate_embedding


class FakeProfiles:
    def resolve(self, kind: str, profile: str) -> dict[str, str]:
        if profile == "unknown-profile":
            raise ValueError("unknown profile")
        return {"provider": "phi4-local", "model": "phi4:14b-q4_K_M"}


class FakeLLM:
    def __init__(self) -> None:
        self.profiles = FakeProfiles()
        self.chat_calls: list[Any] = []
        self.embed_calls: list[Any] = []
        self.paths: list[str] = []

    async def chat(self, request: Any) -> dict[str, Any]:
        if request.profile and (request.provider or request.model):
            raise HTTPException(400, "profile and provider/model are exclusive")
        if request.profile == "unknown-profile":
            raise HTTPException(400, "unknown profile")
        self.chat_calls.append(request)
        return {
            "text": '{"has_second_topic": false, "boundary_id": null}',
            "parsed": {"has_second_topic": False, "boundary_id": None},
            "profile": request.profile,
            "provider": "phi4-local",
            "model": "phi4:14b-q4_K_M",
        }

    async def embed(self, request: Any) -> dict[str, Any]:
        self.embed_calls.append(request)
        return {
            "embedding": [0.0] * EMBEDDING_DIMENSION,
            "dim": EMBEDDING_DIMENSION,
            "profile": request.profile,
            "provider": "ollama",
            "model": "nomic-embed-text",
        }


@pytest.fixture
def gateway_client(monkeypatch: pytest.MonkeyPatch) -> tuple[GatewayHTTPClient, FakeLLM]:
    monkeypatch.setenv("AI_OS_TOKEN", "test-token")
    app = create_app(token="test-token")
    service = FakeLLM()
    @app.middleware("http")
    async def record_path(request: Any, call_next: Any) -> Any:
        service.paths.append(request.url.path)
        return await call_next(request)
    app.dependency_overrides[get_llm_service] = lambda: service
    http = TestClient(app, base_url="http://gateway.test")
    return GatewayHTTPClient(base_url="http://gateway.test", client=http), service


def test_resolves_the_document_segmentation_profile(gateway_client: tuple[GatewayHTTPClient, FakeLLM]) -> None:
    client, _ = gateway_client
    result = client.resolve_chat_profile("document-segmentation-v1")
    assert result == {"provider": "phi4-local", "model": "phi4:14b-q4_K_M"}


def test_structured_chat_returns_parsed_for_an_ingestion_schema(gateway_client: tuple[GatewayHTTPClient, FakeLLM]) -> None:
    client, service = gateway_client
    response = client.chat(
        "segment this document",
        profile="document-segmentation-v1",
        response_format={"type": "json_schema", "schema": {"type": "object"}},
    )
    assert response["parsed"] == {"has_second_topic": False, "boundary_id": None}
    assert len(service.chat_calls) == 1
    assert service.chat_calls[0].profile == "document-segmentation-v1"
    assert service.paths == ["/api/llm/chat"]


def test_embedding_through_chunker_profile_validates_model_and_dimension(gateway_client: tuple[GatewayHTTPClient, FakeLLM]) -> None:
    client, service = gateway_client
    response = client.embed("a passage", profile="chunker-v1")
    validate_embedding(response)
    assert len(service.embed_calls) == 1


def test_unknown_profile_fails_explicitly(gateway_client: tuple[GatewayHTTPClient, FakeLLM]) -> None:
    client, _ = gateway_client
    with pytest.raises(GatewayHTTPError) as error:
        client.chat("hello", profile="unknown-profile")
    assert error.value.status_code == 400


def test_unavailable_pinned_profile_fails_explicitly_with_no_fallback(gateway_client: tuple[GatewayHTTPClient, FakeLLM]) -> None:
    client, service = gateway_client
    with pytest.raises(GatewayHTTPError):
        client.chat("hello", profile="unknown-profile")
    assert service.chat_calls == []


def test_profile_plus_provider_in_the_same_request_is_rejected(gateway_client: tuple[GatewayHTTPClient, FakeLLM]) -> None:
    client, service = gateway_client
    with pytest.raises(GatewayHTTPError) as error:
        client.chat("hello", profile="knowledge-extraction-v1", provider="ollama")
    assert error.value.status_code == 400
    assert service.chat_calls == []
