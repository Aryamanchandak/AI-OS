from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import websockets
from pydantic import ValidationError

from glc.channels.catalogue.whatsapp.ws_client import GatewayWSClient
from glc.channels.envelope import ChannelMessage, ChannelReply

VALID_TOKEN = "test-install-token"


@pytest_asyncio.fixture(loop_scope="function")
async def mock_gateway():
    state: dict[str, object] = {
        "expected_token": VALID_TOKEN,
        "response_override": None,
        "response_delay": 0.0,
        "active_connections": 0,
        "max_active_connections": 0,
    }

    async def handler(websocket):
        auth_header = websocket.request.headers.get("Authorization")
        expected_header = f"Bearer {state['expected_token']}"
        if websocket.request.path != "/v1/channels/whatsapp" or auth_header != expected_header:
            await websocket.close(code=1008)
            return

        state["active_connections"] = int(state["active_connections"]) + 1
        state["max_active_connections"] = max(
            int(state["max_active_connections"]),
            int(state["active_connections"]),
        )
        while True:
            try:
                raw = await websocket.recv()
            except websockets.exceptions.ConnectionClosed:
                state["active_connections"] = int(state["active_connections"]) - 1
                return

            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")

            override = state["response_override"]
            delay = float(state["response_delay"])
            if delay:
                await asyncio.sleep(delay)
            if override == "no_response":
                continue
            if isinstance(override, bytes):
                await websocket.send(override)
                continue
            if isinstance(override, dict):
                await websocket.send(json.dumps(override))
                continue

            try:
                payload = json.loads(raw)
                msg = ChannelMessage.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                await websocket.send(json.dumps({"error": f"invalid envelope: {exc}"}))
                continue

            reply = ChannelReply(
                channel=msg.channel,
                channel_user_id=msg.channel_user_id,
                text=f"[glc echo] {msg.text or ''}",
                thread_id=msg.thread_id,
            )
            await websocket.send(reply.model_dump_json())

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    state["url"] = f"ws://127.0.0.1:{port}/v1/channels/whatsapp"

    try:
        yield state
    finally:
        server.close()
        await server.wait_closed()


def _make_msg(**overrides) -> ChannelMessage:
    defaults = {
        "channel": "whatsapp",
        "channel_user_id": "919999990000",
        "user_handle": "owner",
        "text": "hello",
        "trust_level": "owner_paired",
        "arrived_at": datetime.now(UTC),
        "metadata": {"provider": "meta", "message_id": "wamid.test"},
    }
    return ChannelMessage(**(defaults | overrides))


@pytest.mark.asyncio
async def test_send_and_receive_returns_channel_reply(mock_gateway):
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)
    await client.connect()

    try:
        reply = await client.send_and_receive(_make_msg())
    finally:
        await client.close()

    assert isinstance(reply, ChannelReply)
    assert reply.channel == "whatsapp"
    assert reply.channel_user_id == "919999990000"
    assert reply.text == "[glc echo] hello"


@pytest.mark.asyncio
async def test_gateway_drop_error_returned_as_dict(mock_gateway):
    mock_gateway["response_override"] = {"error": "dropped: user not allowlisted"}
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)
    await client.connect()

    try:
        result = await client.send_and_receive(_make_msg())
    finally:
        await client.close()

    assert result == {"error": "dropped: user not allowlisted"}


@pytest.mark.asyncio
async def test_gateway_rate_limit_returned_as_dict(mock_gateway):
    mock_gateway["response_override"] = {"status": 429, "error": "rate limited"}
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)
    await client.connect()

    try:
        result = await client.send_and_receive(_make_msg())
    finally:
        await client.close()

    assert result == {"status": 429, "error": "rate limited"}


@pytest.mark.asyncio
async def test_async_context_manager_connects_and_closes(mock_gateway):
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)

    async with client as connected:
        assert connected is client
        assert client._ws is not None

    assert client._ws is None


@pytest.mark.asyncio
async def test_send_without_connect_raises():
    client = GatewayWSClient(url="ws://127.0.0.1:9/v1/channels/whatsapp", token=VALID_TOKEN)

    with pytest.raises(RuntimeError, match="not connected"):
        await client.send_and_receive(_make_msg())


@pytest.mark.asyncio
async def test_send_and_receive_serializes_concurrent_calls(mock_gateway):
    mock_gateway["response_delay"] = 0.05
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)
    await client.connect()

    first = _make_msg(text="first", thread_id="thread-1")
    second = _make_msg(text="second", thread_id="thread-2")

    try:
        reply1, reply2 = await asyncio.gather(
            client.send_and_receive(first),
            client.send_and_receive(second),
        )
    finally:
        await client.close()

    assert isinstance(reply1, ChannelReply)
    assert isinstance(reply2, ChannelReply)
    assert reply1.text == "[glc echo] first"
    assert reply1.thread_id == "thread-1"
    assert reply2.text == "[glc echo] second"
    assert reply2.thread_id == "thread-2"


@pytest.mark.asyncio
async def test_send_and_receive_times_out_when_gateway_stalls(mock_gateway):
    mock_gateway["response_override"] = "no_response"
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN, receive_timeout=0.05)
    await client.connect()

    try:
        with pytest.raises(TimeoutError, match="timed out waiting for a reply"):
            await client.send_and_receive(_make_msg())
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_connect_closes_previous_connection_before_reconnect(mock_gateway):
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)
    await client.connect()
    first_ws = client._ws

    await client.connect()
    second_ws = client._ws

    try:
        assert second_ws is not None
        assert second_ws is not first_ws
        assert first_ws.close_code is not None
        assert mock_gateway["max_active_connections"] == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_null_error_field_still_returns_channel_reply(mock_gateway):
    mock_gateway["response_override"] = {
        "error": None,
        "channel": "whatsapp",
        "channel_user_id": "919999990000",
        "text": "[glc echo] hello",
        "thread_id": None,
    }
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)
    await client.connect()

    try:
        reply = await client.send_and_receive(_make_msg())
    finally:
        await client.close()

    assert isinstance(reply, ChannelReply)
    assert reply.text == "[glc echo] hello"


@pytest.mark.asyncio
async def test_invalid_gateway_reply_is_returned_as_error_dict(mock_gateway):
    mock_gateway["response_override"] = {"status": 503, "message": "upstream unavailable"}
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)
    await client.connect()

    try:
        result = await client.send_and_receive(_make_msg())
    finally:
        await client.close()

    assert result["error"] == "invalid gateway reply"
    assert result["status"] == 503
    assert result["raw"] == {"status": 503, "message": "upstream unavailable"}


@pytest.mark.asyncio
async def test_binary_reply_with_invalid_utf8_returns_error_dict(mock_gateway):
    mock_gateway["response_override"] = b"\xff\xfe\xfd"
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)
    await client.connect()

    try:
        result = await client.send_and_receive(_make_msg())
    finally:
        await client.close()

    assert result["error"] == "invalid gateway reply encoding"
    assert result["status"] == 502


@pytest.mark.asyncio
async def test_closed_socket_raises_runtime_error(mock_gateway):
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)
    await client.connect()
    await client._ws.close()

    with pytest.raises(RuntimeError, match="not connected"):
        await client.send_and_receive(_make_msg())

    assert client._ws is None


@pytest.mark.asyncio
async def test_aexit_preserves_original_exception_when_close_fails(mock_gateway):
    client = GatewayWSClient(url=mock_gateway["url"], token=VALID_TOKEN)

    async def broken_close() -> None:
        raise RuntimeError("close failed")

    client.close = broken_close  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="root cause") as exc_info:
        async with client:
            raise ValueError("root cause")

    assert "close failed" in "".join(exc_info.value.__notes__)


def test_init_does_not_touch_install_token_when_token_is_provided():
    with patch(
        "glc.channels.catalogue.whatsapp.ws_client.get_or_create_install_token",
        side_effect=AssertionError("should not be called"),
    ):
        GatewayWSClient(token="explicit-token")


def test_init_does_not_touch_install_token_when_token_is_omitted():
    with patch(
        "glc.channels.catalogue.whatsapp.ws_client.get_or_create_install_token",
        side_effect=AssertionError("should not be called"),
    ):
        GatewayWSClient()


@pytest.mark.asyncio
async def test_connect_resolves_install_token_lazily():
    with patch(
        "glc.channels.catalogue.whatsapp.ws_client.get_or_create_install_token",
        return_value=VALID_TOKEN,
    ) as token_mock:
        client = GatewayWSClient(url="ws://localhost:8111/v1/channels/whatsapp")
        with patch(
            "glc.channels.catalogue.whatsapp.ws_client.websockets.connect",
            new=AsyncMock(return_value=object()),
        ):
            await client.connect()

    token_mock.assert_called_once()


def test_invalid_glc_port_is_rejected(monkeypatch):
    monkeypatch.setenv("GLC_PORT", "8111/v1/../admin")

    with pytest.raises(ValueError, match="numeric TCP port"):
        GatewayWSClient()


def test_non_local_insecure_ws_url_is_rejected():
    with pytest.raises(ValueError, match="only allowed for localhost"):
        GatewayWSClient(url="ws://example.com/v1/channels/whatsapp", token=VALID_TOKEN)


@pytest.mark.asyncio
async def test_header_auth_accepts_tokens_with_special_characters(mock_gateway):
    token = "token+with/slash=="
    mock_gateway["expected_token"] = token
    client = GatewayWSClient(url=mock_gateway["url"], token=token)
    await client.connect()

    try:
        reply = await client.send_and_receive(_make_msg())
    finally:
        await client.close()

    assert isinstance(reply, ChannelReply)
