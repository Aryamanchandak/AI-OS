"""Leak 9 — cross-channel envelope spoofing.

An adapter (or anything that can reach WS /v1/channels/{name}) could send a
ChannelMessage whose ``channel`` field doesn't match the route it connected
to — e.g. claim ``channel="discord"`` while connected to
``/v1/channels/telegram``. Before the fix the gateway never checked the two
match, so a compromised telegram adapter could inject messages that get
processed (and audited) as if they came from a totally different channel.
"""

from __future__ import annotations

import json

from glc.audit.store import query


def _envelope(channel: str, channel_user_id: str = "u1", trust_level: str = "untrusted") -> dict:
    return {
        "channel": channel,
        "channel_user_id": channel_user_id,
        "user_handle": channel_user_id,
        "trust_level": trust_level,
        "arrived_at": "2026-07-16T00:00:00Z",
    }


def test_mismatched_envelope_channel_is_rejected_and_closed(app_client, install_token):
    with app_client.websocket_connect(
        "/v1/channels/webui",
        headers={"Authorization": f"Bearer {install_token}"},
    ) as ws:
        ws.send_text(json.dumps(_envelope(channel="discord")))
        data = json.loads(ws.receive_text())
        assert "does not match route" in data["error"]

        # the gateway must close the socket, not just drop the one message
        import pytest
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()

    rows = query(limit=10)
    mismatch_rows = [r for r in rows if r["event_type"] == "envelope_channel_mismatch"]
    assert len(mismatch_rows) == 1
    assert mismatch_rows[0]["channel"] == "webui"
    assert "discord" in mismatch_rows[0]["result_json"]


def test_matching_envelope_channel_is_processed_normally(app_client, install_token):
    from glc.security.pairing import get_pairing_store

    get_pairing_store().force_pair_owner("webui", "u1")

    with app_client.websocket_connect(
        "/v1/channels/webui",
        headers={"Authorization": f"Bearer {install_token}"},
    ) as ws:
        ws.send_text(json.dumps(_envelope(channel="webui", channel_user_id="u1")))
        data = json.loads(ws.receive_text())
        assert data.get("channel") == "webui"
        assert "[glc echo]" in (data.get("text") or "")

    rows = query(limit=10)
    assert any(r["event_type"] == "inbound_message" and r["channel"] == "webui" for r in rows)
    assert not any(r["event_type"] == "envelope_channel_mismatch" for r in rows)
