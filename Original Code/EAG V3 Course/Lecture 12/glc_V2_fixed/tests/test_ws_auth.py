"""C3 — WS install token must travel only in the Authorization header, never
the query string. Query strings land in access/proxy logs; a token that can
be authenticated via `?token=...` is a token leaking into those logs.

Before the fix, `channel_ws` accepted the token via `?token=` as a fallback
whenever no Authorization header was presented. This test proves that path
is gone: a connection carrying only `?token=<valid token>` is now rejected
exactly like a connection with no credential at all, while the header path
keeps working (covered by test_channel_envelope_spoofing.py's passing
cases).
"""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect


def test_query_string_token_is_no_longer_accepted(app_client, install_token):
    with pytest.raises(WebSocketDisconnect):
        with app_client.websocket_connect(f"/v1/channels/webui?token={install_token}"):
            pass


def test_no_credential_at_all_is_rejected(app_client):
    with pytest.raises(WebSocketDisconnect):
        with app_client.websocket_connect("/v1/channels/webui"):
            pass


def test_header_token_still_works(app_client, install_token):
    from glc.security.pairing import get_pairing_store

    get_pairing_store().force_pair_owner("webui", "u1")

    with app_client.websocket_connect(
        "/v1/channels/webui",
        headers={"Authorization": f"Bearer {install_token}"},
    ) as ws:
        import json

        ws.send_text(
            json.dumps(
                {
                    "channel": "webui",
                    "channel_user_id": "u1",
                    "user_handle": "u1",
                    "trust_level": "untrusted",
                    "arrived_at": "2026-07-16T00:00:00Z",
                }
            )
        )
        data = json.loads(ws.receive_text())
        assert "[glc echo]" in (data.get("text") or "")
