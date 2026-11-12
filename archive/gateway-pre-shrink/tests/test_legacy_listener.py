from __future__ import annotations

import logging
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from gateway.compatibility import legacy_listener
from gateway.platform.service_registry import gateway_address


def test_launcher_uses_registry_override(tmp_path: Path) -> None:
    registry = tmp_path / "services.yaml"
    registry.write_text(
        "services:\n  gateway: {host: 127.0.0.1, port: 8199, enabled: true, required: true}\n",
        encoding="utf-8",
    )
    assert gateway_address(registry).port == 8199


def test_legacy_http_and_sse_forward_without_logging_content(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    registry = tmp_path / "services.yaml"
    registry.write_text(
        "services:\n"
        "  gateway: {host: 127.0.0.1, port: 8199, enabled: true, required: true}\n"
        "  glc_legacy: {host: 127.0.0.1, port: 8198, enabled: true}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_OS_SERVICE_REGISTRY_PATH", str(registry))

    upstream = FastAPI()

    @upstream.post("/v1/chat")
    async def chat() -> dict[str, bool]:
        return {"ok": True}

    @upstream.get("/v1/events")
    async def events() -> StreamingResponse:
        async def chunks():
            yield "data: one\n\n"
            yield "data: two\n\n"

        return StreamingResponse(chunks(), media_type="text/event-stream")

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(transport=httpx.ASGITransport(app=upstream), **kwargs)

    monkeypatch.setattr(legacy_listener.httpx, "AsyncClient", client_factory)
    with caplog.at_level(logging.WARNING, logger="gateway.legacy_listener"):
        with TestClient(legacy_listener.app) as client:
            response = client.post("/v1/chat?secret=never-log-this", json={"prompt": "never-log-this"})
            stream = client.get("/v1/events")
    assert response.json() == {"ok": True}
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert stream.text == "data: one\n\ndata: two\n\n"
    assert caplog.text.count("legacy_connection protocol=http") == 2
    assert "never-log-this" not in caplog.text
