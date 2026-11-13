"""WebSocket client for routing WhatsApp envelopes through the gateway.

PARKED (backlog B2, see help_docs/HANDOFF.md §7.16): not wired to any
caller. help_docs/INBOUND_WEBHOOK_ARCHITECTURE.md's Approach 2 (US-13,
demo_webhook_server.py) calls the adapter directly and bypasses the
gateway; only Approach 3 (POST /v1/channels/{name}/webhook in
glc/routes/channels.py, shared code, separate maintainer PR, out of
scope for US-1 through US-15) would route through the gateway, and that
doc explicitly says B2's scope needs revision in light of Approach 3.
Kept here as groundwork in case Approach 3 lands; do not treat as demoable.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.parse import urlparse

import websockets
from pydantic import ValidationError

from glc.channels.envelope import ChannelMessage, ChannelReply
from glc.config import get_or_create_install_token


class GatewayWSClient:
    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        channel: str = "whatsapp",
        receive_timeout: float = 30.0,
    ) -> None:
        self._url = self._validate_url(url or self._default_url(channel))
        self._token = token
        self._receive_timeout = receive_timeout
        self._ws: Any | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._lock:
            if self._ws is not None:
                await self._ws.close()
                self._ws = None
            self._ws = await self._open_websocket()

    async def send_and_receive(self, msg: ChannelMessage) -> ChannelReply | dict[str, Any]:
        async with self._lock:
            if self._is_closed():
                self._ws = None
                raise RuntimeError("GatewayWSClient is not connected")

            try:
                await self._ws.send(msg.model_dump_json())
                raw = await asyncio.wait_for(self._ws.recv(), timeout=self._receive_timeout)
            except websockets.exceptions.ConnectionClosed as exc:
                self._ws = None
                raise RuntimeError("GatewayWSClient is not connected") from exc
            except TimeoutError as exc:
                raise TimeoutError(
                    f"GatewayWSClient timed out waiting for a reply after {self._receive_timeout} seconds"
                ) from exc

            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8")
                except UnicodeDecodeError as exc:
                    return {
                        "error": "invalid gateway reply encoding",
                        "status": 502,
                        "details": str(exc),
                    }
            data = json.loads(raw)
            if data.get("error") is not None or data.get("status") == 429:
                return data
            sanitized = dict(data)
            if sanitized.get("error") is None:
                sanitized.pop("error", None)
            try:
                return ChannelReply.model_validate(sanitized)
            except ValidationError as exc:
                return {
                    "error": "invalid gateway reply",
                    "status": data.get("status", 502),
                    "details": exc.errors(),
                    "raw": data,
                }

    async def close(self) -> None:
        async with self._lock:
            if self._ws is not None:
                await self._ws.close()
                self._ws = None

    async def __aenter__(self) -> GatewayWSClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            await self.close()
        except Exception as close_exc:
            if exc is not None:
                exc.add_note(f"GatewayWSClient.close() also failed: {close_exc!r}")
                return
            raise

    async def _open_websocket(self) -> Any:
        headers = {"Authorization": f"Bearer {self._resolve_token()}"}
        try:
            return await websockets.connect(self._url, additional_headers=headers)
        except TypeError:
            return await websockets.connect(self._url, extra_headers=headers)

    def _resolve_token(self) -> str:
        if self._token is None:
            self._token = get_or_create_install_token()
        return self._token

    def _is_closed(self) -> bool:
        if self._ws is None:
            return True
        return bool(getattr(self._ws, "closed", False) or getattr(self._ws, "close_code", None) is not None)

    @staticmethod
    def _default_url(channel: str) -> str:
        port = os.environ.get("GLC_PORT", "8111")
        if not port.isdigit():
            raise ValueError(f"GLC_PORT must be a numeric TCP port, got {port!r}")
        port_num = int(port)
        if port_num < 1 or port_num > 65535:
            raise ValueError(f"GLC_PORT must be between 1 and 65535, got {port_num}")
        return f"ws://localhost:{port_num}/v1/channels/{channel}"

    @staticmethod
    def _validate_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"ws", "wss"}:
            raise ValueError(f"Gateway websocket URL must use ws:// or wss://, got {url!r}")
        if not parsed.netloc:
            raise ValueError(f"Gateway websocket URL must include a host, got {url!r}")
        if parsed.scheme == "ws" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Insecure ws:// transport is only allowed for localhost connections")
        return url
