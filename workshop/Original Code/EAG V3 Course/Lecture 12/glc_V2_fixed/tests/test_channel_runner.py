"""glc/channels/runner.py — the ADAPTER side of the channel-scoped
credential fix (see test_channel_scoped_credentials.py for the gateway
side). The full end-to-end proof (adapter container really has no
GLC_INSTALL_TOKEN, really gets rejected by /v1/control/pair) only runs
inside a real Modal deployment via verify_isolation() + the sandboxed
Functions in modal_app.py — these tests cover the parts that are testable
locally: channel_token() reads exactly GLC_CHANNEL_TOKEN (never
GLC_INSTALL_TOKEN), and relay() sends it as the WS bearer.
"""

from __future__ import annotations

import pytest

from glc.channels.runner import channel_token, gateway_http_base, gateway_ws_url


def test_channel_token_reads_glc_channel_token(monkeypatch):
    monkeypatch.setenv("GLC_CHANNEL_TOKEN", "abc123")
    assert channel_token() == "abc123"


def test_channel_token_raises_when_unset(monkeypatch):
    monkeypatch.delenv("GLC_CHANNEL_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="GLC_CHANNEL_TOKEN"):
        channel_token()


def test_channel_token_ignores_install_token(monkeypatch):
    """The keystone property from the adapter's own side: even if
    GLC_INSTALL_TOKEN somehow ended up in the environment, channel_token()
    must never read it — only GLC_CHANNEL_TOKEN authenticates this adapter."""
    monkeypatch.setenv("GLC_INSTALL_TOKEN", "raw-control-plane-token")
    monkeypatch.delenv("GLC_CHANNEL_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="GLC_CHANNEL_TOKEN"):
        channel_token()


def test_gateway_ws_url_and_http_base(monkeypatch):
    monkeypatch.setenv("GLC_GATEWAY_WS_URL", "wss://example--gw.modal.run")
    assert gateway_ws_url("relay_echo") == "wss://example--gw.modal.run/v1/channels/relay_echo"
    assert gateway_http_base() == "https://example--gw.modal.run"


async def test_relay_sends_channel_token_not_install_token(monkeypatch):
    """relay() must authenticate with channel_token(), never any install
    token — proven by inspecting the actual Authorization header it sends,
    with the websockets connection mocked out (no real network)."""
    import glc.channels.runner as runner_mod
    from glc.channels.envelope import ChannelReply

    monkeypatch.setenv("GLC_GATEWAY_WS_URL", "wss://example--gw.modal.run")
    monkeypatch.setenv("GLC_CHANNEL_TOKEN", "scoped-channel-token")
    monkeypatch.setenv("GLC_INSTALL_TOKEN", "raw-control-plane-token")  # must NOT be used

    captured_headers = {}

    class _FakeWS:
        async def send(self, _data):
            pass

        async def recv(self):
            return ChannelReply(channel="relay_echo", channel_user_id="u1", text="hi").model_dump_json()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _FakeWebsocketsModule:
        @staticmethod
        def connect(url, additional_headers=None, **kwargs):
            captured_headers.update(additional_headers or {})
            return _FakeWS()

    monkeypatch.setitem(__import__("sys").modules, "websockets", _FakeWebsocketsModule())

    adapter = runner_mod.EchoIngressAdapter()
    result = await runner_mod.relay(adapter, {"channel_user_id": "u1", "text": "hi"})

    assert result["status"] == "ok"
    assert captured_headers.get("Authorization") == "Bearer scoped-channel-token"
