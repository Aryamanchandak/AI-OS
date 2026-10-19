from __future__ import annotations

import asyncio

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from gateway.app.dependencies import get_llm_service
from gateway.app.main import create_app
from gateway.platform.observability import Telemetry
from gateway.platform.observability.capture import RefusalLog


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key, filename in {
        "GLC_GATEWAY_DB": "ledger", "GLC_AUDIT_DB": "audit",
        "GLC_PAIRING_DB": "pairings",
        "GLC_INSTALL_TOKEN_FILE": "install-token",
    }.items():
        monkeypatch.setenv(key, str(tmp_path / filename))
    with TestClient(create_app(token="test-token")) as active:
        yield active


HEADERS = {"Authorization": "Bearer test-token"}


def test_preflight_probes_and_redacts_partial_failure(client):
    class LLM:
        async def chat(self, request):
            assert request.max_tokens == 8
            return {"provider": "test", "model": "chat", "profile": request.profile}

        async def embed(self, request):
            raise HTTPException(503, "Authorization: Bearer secret-provider-key")

    client.app.dependency_overrides[get_llm_service] = lambda: LLM()
    response = client.post("/api/llm/preflight", headers=HEADERS, json={"chat_profile": "probe"})
    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is False and result["chat"]["ok"] is True
    assert result["embedding"]["status_code"] == 503
    assert "secret-provider-key" not in response.text
    assert result["embedding"]["profile"] == "chunker-v1"
    assert set(result) == {"ok", "chat", "embedding"}


def test_preflight_both_probes_succeed(client):
    class LLM:
        async def chat(self, request):
            return {"provider": "test", "model": "chat"}

        async def embed(self, request):
            return {"provider": "test", "model": "embed", "dim": 768}

    client.app.dependency_overrides[get_llm_service] = lambda: LLM()
    response = client.post("/api/llm/preflight", headers=HEADERS, json={})
    assert response.json()["ok"] is True
    assert response.json()["embedding"]["dim"] == 768


def test_real_http_traces_and_refusals_are_readable_without_content(client):
    class LLM:
        async def chat(self, request):
            raise HTTPException(402, {"code": "budget_exceeded", "limit_usd": 0, "prompt": request.prompt, "message": "Bearer secret-test-token"})

    client.app.dependency_overrides[get_llm_service] = lambda: LLM()
    assert client.post("/api/llm/chat?credential=never-capture-query", headers=HEADERS, json={"prompt": "never-capture-prompt"}).status_code == 402
    assert client.get("/api/observability/refusals").status_code == 401
    response = client.get("/api/observability/refusals", headers=HEADERS)
    assert response.json()["total"] == 1
    assert response.json()["refusals"][0]["detail"]["limit_usd"] == 0
    assert "never-capture" not in response.text and "secret-test-token" not in response.text
    recent = client.get("/api/observability/traces/recent", headers=HEADERS).json()
    assert recent["active"] is True and recent["capture_content"] is False
    trace_id = recent["traces"][0]["trace_id"]
    detail = client.get(f"/api/observability/traces/{trace_id}", headers=HEADERS)
    assert detail.status_code == 200 and detail.json()["spans"]
    assert "never-capture" not in detail.text and "secret-test-token" not in detail.text
    assert client.get("/api/observability/traces/unknown", headers=HEADERS).status_code == 404


def test_trace_and_refusal_storage_are_bounded():
    telemetry = Telemetry()
    telemetry.initialize()
    try:
        telemetry.recent.limit = 2
        telemetry.recent.max_spans = 2
        for _ in range(5):
            with telemetry.tracer.start_as_current_span("request"):
                for _ in range(5):
                    with telemetry.tracer.start_as_current_span("child"):
                        pass
        assert len(telemetry.recent.summaries(100)) == 2
        for row in telemetry.recent.summaries(100):
            assert len(telemetry.recent.detail(row["trace_id"])["spans"]) == 2
    finally:
        telemetry.close()
    log = RefusalLog(limit=2)
    for _ in range(5):
        log.record("POST", "/chat", b'{"detail":{"code":"budget_exceeded"}}')
    assert log.describe()["total"] == 5 and log.describe()["kept"] == 2


def test_preflight_timeout_is_a_bounded_failure(client, monkeypatch):
    from gateway.llm.api import preflight as module
    monkeypatch.setattr(module, "PREFLIGHT_TIMEOUT_S", 0.01)
    class LLM:
        async def chat(self, request):
            await asyncio.sleep(10)
        async def embed(self, request):
            return {"provider": "test", "model": "embed", "dim": 768}
    client.app.dependency_overrides[get_llm_service] = lambda: LLM()
    response = client.post("/api/llm/preflight", headers=HEADERS, json={}).json()
    assert response["chat"]["status_code"] == 504
    assert response["embedding"]["ok"] is True


def test_capture_exposes_chat_trace_reference_without_content(client):
    class LLM:
        async def chat(self, request):
            return {"provider": "test", "model": "model", "text": "private answer", "input_tokens": 1, "output_tokens": 2}
    client.app.dependency_overrides[get_llm_service] = lambda: LLM()
    chat = client.post("/api/llm/chat", headers=HEADERS, json={"prompt": "private prompt"}).json()
    detail = client.get(f"/api/observability/traces/{chat['trace']['trace_id']}", headers=HEADERS)
    assert detail.status_code == 200
    assert "private" not in detail.text
    assert detail.json()["spans"][0]["attributes"]["gen_ai.provider.name"] == "test"
    assert client.get("/api/observability/refusals", headers=HEADERS).json()["total"] == 0


def test_real_llm_pipeline_stages_are_traced_even_when_provider_is_unconfigured(client):
    response = client.post("/api/llm/chat", headers=HEADERS, json={"prompt": "probe", "provider": "no-such-provider"})
    assert response.status_code >= 400
    recent = client.get("/api/observability/traces/recent", headers=HEADERS).json()
    detail = client.get(f"/api/observability/traces/{recent['traces'][0]['trace_id']}", headers=HEADERS).json()
    names = {row["name"] for row in detail["spans"]}
    assert "llm.RequestValidationStage" in names
    assert "llm.FinalizationStage" in names
