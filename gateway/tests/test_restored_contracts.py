from __future__ import annotations

import asyncio

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from gateway.app import get_llm_service
from gateway.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key, filename in {
        "GLC_GATEWAY_DB": "ledger",
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


def test_preflight_timeout_is_a_bounded_failure(client, monkeypatch):
    import gateway.app as module
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


@pytest.fixture
def spans(client):
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    client.app.state.telemetry.provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def test_chat_reply_carries_its_trace_id_and_spans_hold_no_content(client, spans):
    class LLM:
        async def chat(self, request):
            return {"provider": "test", "model": "model", "text": "private answer", "input_tokens": 1, "output_tokens": 2}
    client.app.dependency_overrides[get_llm_service] = lambda: LLM()
    chat = client.post("/api/llm/chat", headers=HEADERS, json={"prompt": "private prompt"}).json()
    [root] = [span for span in spans.get_finished_spans() if span.parent is None]
    assert chat["trace"]["trace_id"] == f"{root.context.trace_id:032x}"
    assert root.attributes["gen_ai.provider.name"] == "test"
    assert "private" not in str([dict(span.attributes or {}) for span in spans.get_finished_spans()])


def test_request_span_carries_model_tokens_and_cost_under_gen_ai_names(client, spans):
    # Langfuse reads model, usage and cost from these gen_ai.* attribute names.
    class LLM:
        async def chat(self, request):
            return {"provider": "test", "model": "model", "input_tokens": 1, "output_tokens": 2,
                    "cost": {"total_usd": 0.0125}}
    client.app.dependency_overrides[get_llm_service] = lambda: LLM()
    client.post("/api/llm/chat", headers=HEADERS, json={"prompt": "hi"})
    [root] = [span for span in spans.get_finished_spans() if span.parent is None]
    assert root.attributes["gen_ai.response.model"] == "model"
    assert root.attributes["gen_ai.usage.input_tokens"] == 1
    assert root.attributes["gen_ai.usage.output_tokens"] == 2
    assert root.attributes["gen_ai.usage.cost"] == 0.0125


def test_real_llm_pipeline_stages_are_traced_even_when_provider_is_unconfigured(client, spans):
    response = client.post("/api/llm/chat", headers=HEADERS, json={"prompt": "probe", "provider": "no-such-provider"})
    assert response.status_code >= 400
    names = {span.name for span in spans.get_finished_spans()}
    assert "llm.validate" in names
    assert "llm.finalize" in names
