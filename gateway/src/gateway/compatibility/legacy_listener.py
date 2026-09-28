"""Temporary, observable legacy-port proxy for the Gateway cutover.

Run explicitly with ``python -m gateway.compatibility.legacy_listener``.
Only connection metadata is logged; request paths, headers and bodies are not.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.websockets import WebSocketDisconnect

from gateway.platform.service_registry import DEFAULT_REGISTRY_PATH, load_service_registry


logger = logging.getLogger("gateway.legacy_listener")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _addresses() -> tuple[str, str, str, int]:
    path = Path(os.environ.get("AI_OS_SERVICE_REGISTRY_PATH", str(DEFAULT_REGISTRY_PATH)))
    registry = load_service_registry(path)
    gateway = registry.get("gateway")
    legacy = registry.get("glc_legacy")
    if not gateway.enabled or not legacy.enabled:
        raise ValueError("gateway and glc_legacy must both be enabled")
    return gateway.url, gateway.url.replace("http://", "ws://", 1), legacy.host, legacy.port


def _observe(protocol: str, client_host: str | None) -> None:
    # Python's formatter supplies the timestamp. Never log a URL or query:
    # legacy clients sometimes place credentials in query parameters.
    logger.warning("legacy_connection protocol=%s client=%s", protocol, client_host or "unknown")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def forward_http(path: str, request: Request) -> StreamingResponse:
    gateway_url, _, _, _ = _addresses()
    _observe("http", request.client.host if request.client else None)
    upstream = httpx.AsyncClient(timeout=None)
    url = f"{gateway_url}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    try:
        prepared = upstream.build_request(
            request.method,
            url,
            headers={key: value for key, value in request.headers.items() if key.lower() not in {"host", "content-length"}},
            content=await request.body(),
        )
        response = await upstream.send(prepared, stream=True)
    except BaseException:
        await upstream.aclose()
        raise

    async def close() -> None:
        await response.aclose()
        await upstream.aclose()

    return StreamingResponse(
        response.aiter_raw(),
        status_code=response.status_code,
        headers={key: value for key, value in response.headers.items() if key.lower() not in {"content-length", "transfer-encoding", "connection"}},
        background=BackgroundTask(close),
    )


@app.websocket("/{path:path}")
async def forward_websocket(path: str, socket: WebSocket) -> None:
    import websockets

    _, gateway_ws, _, _ = _addresses()
    _observe("websocket", socket.client.host if socket.client else None)
    uri = f"{gateway_ws}/{path}"
    if socket.url.query:
        uri += f"?{socket.url.query}"
    headers = {}
    if authorization := socket.headers.get("authorization"):
        headers["Authorization"] = authorization
    try:
        async with websockets.connect(uri, additional_headers=headers) as upstream:
            await socket.accept()

            async def to_gateway() -> None:
                while True:
                    message = await socket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message.get("text") is not None:
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])

            async def to_client() -> None:
                async for message in upstream:
                    if isinstance(message, str):
                        await socket.send_text(message)
                    else:
                        await socket.send_bytes(message)

            tasks = [asyncio.create_task(to_gateway()), asyncio.create_task(to_client())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for task in done:
                if error := task.exception():
                    raise error
    except WebSocketDisconnect:
        return
    except Exception:
        logger.warning("legacy_websocket_failure")
        if socket.application_state.name != "DISCONNECTED":
            await socket.close(code=1011)


def main() -> None:
    import uvicorn

    _, _, host, port = _addresses()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logger.warning("legacy_listener_started")
    uvicorn.run(app, host=host, port=port, access_log=False)


if __name__ == "__main__":
    main()
