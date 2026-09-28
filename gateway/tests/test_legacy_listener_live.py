"""Real loopback exercise of the temporary 8111 protocol boundary."""

from __future__ import annotations

import socket
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
import pytest
import uvicorn

from gateway.compatibility import legacy_listener


pytestmark = pytest.mark.skipif(
    os.environ.get("AI_OS_LOOPBACK_TEST") != "1",
    reason="requires localhost socket permission; run with AI_OS_LOOPBACK_TEST=1",
)


def test_http_sse_and_websocket_forward_over_loopback(tmp_path: Path, monkeypatch) -> None:
    upstream = FastAPI()

    @upstream.get("/v1/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    @upstream.get("/v1/events")
    async def events() -> StreamingResponse:
        async def frames():
            yield "data: first\n\n"
            yield "data: second\n\n"

        return StreamingResponse(frames(), media_type="text/event-stream")

    @upstream.websocket("/v1/echo")
    async def echo(socket: WebSocket) -> None:
        await socket.accept()
        await socket.send_text(await socket.receive_text())
        await socket.send_bytes(await socket.receive_bytes())

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    registry = tmp_path / "services.yaml"
    registry.write_text(
        "services:\n"
        f"  gateway: {{host: 127.0.0.1, port: {port}, enabled: true, required: true}}\n"
        "  glc_legacy: {host: 127.0.0.1, port: 8111, enabled: true}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_OS_SERVICE_REGISTRY_PATH", str(registry))

    server = uvicorn.Server(uvicorn.Config(upstream, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with TestClient(legacy_listener.app) as client:
            assert client.get("/v1/ping").json() == {"ok": True}
            stream = client.get("/v1/events")
            assert stream.headers["content-type"].startswith("text/event-stream")
            assert stream.text == "data: first\n\ndata: second\n\n"
            with client.websocket_connect("/v1/echo") as ws:
                ws.send_text("text frame")
                assert ws.receive_text() == "text frame"
                ws.send_bytes(b"binary frame")
                assert ws.receive_bytes() == b"binary frame"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive()
