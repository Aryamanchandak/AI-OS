"""Post-audit hardening: channel-scoped adapter credentials.

Before this fix, every adapter Function mounted the SAME token used to
authenticate `/v1/control/*` (glc.config.get_or_create_install_token /
GLC_INSTALL_TOKEN). A compromised adapter could therefore:
  1. call POST /v1/control/pair with trust_level="owner_paired" and
     self-confirm it (Leak 3 reopened via HTTP), and
  2. open WS /v1/channels/<any other channel> and impersonate it.

glc.security.adapter_auth.derive_channel_token gives each channel its own
token, derived from (but not reversible to) the install token. Adapters now
receive only their own channel's derived token, never the raw install
token. These tests prove the derived token is scoped correctly and that the
gateway's real WS/control-plane checks enforce that scoping end-to-end.
"""

from __future__ import annotations

import json

import pytest
from starlette.websockets import WebSocketDisconnect

from glc.security.adapter_auth import derive_channel_token, verify_channel_token


def test_derive_channel_token_is_deterministic():
    a = derive_channel_token("install-tok", "telegram")
    b = derive_channel_token("install-tok", "telegram")
    assert a == b


def test_derive_channel_token_differs_per_channel():
    tok = "install-tok"
    assert derive_channel_token(tok, "telegram") != derive_channel_token(tok, "discord")


def test_derive_channel_token_differs_per_install_token():
    assert derive_channel_token("tok-a", "telegram") != derive_channel_token("tok-b", "telegram")


def test_verify_channel_token_rejects_wrong_channel():
    tok = "install-tok"
    telegram_token = derive_channel_token(tok, "telegram")
    assert verify_channel_token(tok, "telegram", telegram_token) is True
    assert verify_channel_token(tok, "discord", telegram_token) is False


def test_verify_channel_token_rejects_none_and_empty():
    tok = "install-tok"
    assert verify_channel_token(tok, "telegram", None) is False
    assert verify_channel_token(tok, "telegram", "") is False


def _envelope(channel: str, channel_user_id: str = "u1") -> dict:
    return {
        "channel": channel,
        "channel_user_id": channel_user_id,
        "user_handle": channel_user_id,
        "trust_level": "untrusted",
        "arrived_at": "2026-07-16T00:00:00Z",
    }


def test_channel_token_authenticates_its_own_route(app_client, install_token):
    """A whatsapp-scoped token opens WS /v1/channels/whatsapp and gets
    processed normally — the scoped credential is not just theoretical, it
    is what the gateway's WS handler actually accepts. (whatsapp is
    enabled by default in the packaged channels.yaml; telegram is not.)"""
    from glc.security.pairing import get_pairing_store

    get_pairing_store().force_pair_owner("whatsapp", "u1")
    tok = derive_channel_token(install_token, "whatsapp")

    with app_client.websocket_connect(
        "/v1/channels/whatsapp",
        headers={"Authorization": f"Bearer {tok}"},
    ) as ws:
        ws.send_text(json.dumps(_envelope("whatsapp", "u1")))
        data = json.loads(ws.receive_text())
        assert "[glc echo]" in (data.get("text") or "")


def test_channel_token_cannot_authenticate_a_different_channel_route(app_client, install_token):
    """The core scoping property: a token derived for 'telegram' must be
    rejected on the 'discord' route, even before any envelope is sent — the
    binding happens at the WS handshake, not just via the envelope-channel
    match check (Leak 9)."""
    telegram_tok = derive_channel_token(install_token, "telegram")

    with pytest.raises(WebSocketDisconnect):
        with app_client.websocket_connect(
            "/v1/channels/discord",
            headers={"Authorization": f"Bearer {telegram_tok}"},
        ):
            pass


def test_channel_token_cannot_authenticate_control_plane(app_client, install_token):
    """The keystone property: holding only a channel-scoped token must NOT
    be enough to call /v1/control/pair (or any other control-plane route).
    Before the fix, adapters held the exact install token and this request
    would succeed with a 200 and a pairing code the caller could immediately
    self-confirm as owner_paired."""
    channel_tok = derive_channel_token(install_token, "relay_echo")

    r = app_client.post(
        "/v1/control/pair",
        headers={"Authorization": f"Bearer {channel_tok}"},
        json={"channel": "attacker", "channel_user_id": "x", "trust_level": "owner_paired"},
    )
    assert r.status_code == 403

    r2 = app_client.get(
        "/v1/control/presence",
        headers={"Authorization": f"Bearer {channel_tok}"},
    )
    assert r2.status_code == 403


def test_raw_install_token_still_works_for_ws_admin_access(app_client, install_token):
    """The raw install token remains a valid superset admin credential for
    WS (used by the WebUI channel / dev tooling / tests) — it's the
    *distribution* to adapter Functions that changed, not this check."""
    from glc.security.pairing import get_pairing_store

    get_pairing_store().force_pair_owner("webui", "u1")

    with app_client.websocket_connect(
        "/v1/channels/webui",
        headers={"Authorization": f"Bearer {install_token}"},
    ) as ws:
        ws.send_text(json.dumps(_envelope("webui", "u1")))
        data = json.loads(ws.receive_text())
        assert "[glc echo]" in (data.get("text") or "")


def test_ws_handler_reclassifies_trust_and_ignores_adapter_claim(app_client, install_token):
    """Invariant 2: the gateway must re-derive trust from its own pairing
    store, not trust the adapter-supplied env.trust_level. A sender who is
    allowlisted but NOT paired at all claims trust_level="owner_paired" in
    the envelope; the audit record must still show the real, gateway-derived
    "untrusted" — proving the claim was never trusted, only recomputed."""
    import yaml

    from glc.audit.store import query
    from glc.config import CONFIG_DIR

    (CONFIG_DIR / "channels.yaml").write_text(
        yaml.dump({"channels": {"telegram": {"allowed_senders": ["spoofer"]}}})
    )

    tok = derive_channel_token(install_token, "telegram")
    with app_client.websocket_connect(
        "/v1/channels/telegram",
        headers={"Authorization": f"Bearer {tok}"},
    ) as ws:
        env = _envelope("telegram", "spoofer")
        env["trust_level"] = "owner_paired"  # unverified adapter claim
        ws.send_text(json.dumps(env))
        ws.receive_text()

    rows = query(limit=10)
    inbound = [r for r in rows if r["event_type"] == "inbound_message" and r["channel_user_id"] == "spoofer"]
    assert inbound, "expected the message to reach the audit log"
    assert inbound[0]["trust_level"] == "untrusted"
