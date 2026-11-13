from __future__ import annotations

import json

import httpx
import pytest

from s13code.gateway import GatewayClient


@pytest.mark.asyncio
async def test_s13code_calls_gateway_without_owning_provider_keys(monkeypatch):
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"text": "done", "provider": "gemini_2", "model": "gemini"})

    monkeypatch.setenv("S13_GATEWAY_PROVIDER", "gemini")
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        result = await GatewayClient("http://127.0.0.1:8111", client=http).complete(
            "Investigate the papers", "Use evidence", session="proof-run"
        )

    assert captured["url"] == "http://127.0.0.1:8111/v1/chat"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["provider"] == "gemini"
    assert payload["agent"] == "s13_answer"
    assert payload["session"] == "proof-run"
    assert not any("key" in field.lower() or "secret" in field.lower() for field in payload)
    assert result["provider"] == "gemini_2"


def test_s13code_does_not_reimplement_gateway_routes(app_client):
    assert app_client.post("/v1/chat", json={}).status_code == 404
    assert app_client.get("/v1/providers").status_code == 404


@pytest.mark.asyncio
async def test_comparison_can_select_provider_and_retain_only_reported_usage(monkeypatch):
    payloads = []

    async def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"text": "done", "provider": "advisor-slot", "model": "review-model",
            "input_tokens": 120, "output_tokens": 40, "latency_ms": 25, "stop_reason": "end_turn",
            "internal_secret": "never-forward"})

    monkeypatch.setenv("S13_GATEWAY_PROVIDER", "default-worker")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        gateway = GatewayClient("http://gateway.test", client=http)
        result = await gateway.complete("question", "system", provider="advisor-slot")
        await gateway.complete("question", "system")
    assert [payload["provider"] for payload in payloads] == ["advisor-slot", "default-worker"]
    assert result["input_tokens"] == 120 and result["output_tokens"] == 40
    assert result["latency_ms"] == 25
    assert "internal_secret" not in result
    assert "cost" not in result  # Missing usage/cost is not invented or treated as free.
