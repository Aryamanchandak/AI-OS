"""WS /v1/channels/{name} — adapter control plane.

Adapters connect over WebSocket and exchange JSON-serialised
ChannelMessage and ChannelReply envelopes. The connection is gated by a
bearer token presented ONLY in the Authorization header
(``Authorization: Bearer <token>``) — either the raw install token (the
admin/dev credential, kept only by the gateway operator and never handed
to an adapter Function) or this channel's own scoped token from
``glc.security.adapter_auth`` (what real adapter deployments actually
receive; see that module's docstring for why the two are no longer the
same credential).

C3 hardening: this used to also accept the token as a ``?token=`` query
string fallback. Query strings land in access logs, proxy logs, and
browser history — exactly where a bearer credential shouldn't be. The
fallback is removed; every caller (the production adapter relay in
``glc/channels/runner.py`` and the dev harnesses) already sends the header.

This endpoint is the contract surface adapters speak to. The gateway
processes incoming messages through the rate limiter, allowlist,
trust-level classifier, policy engine, and (eventually) the agent
runtime. For S11 the agent runtime is a stub that echoes the message
back so adapter authors can verify their wire is plumbed correctly.
"""

from __future__ import annotations

import hmac
import json
import os

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse, PlainTextResponse

from glc.audit import append as audit_append
from glc.channels import registry
from glc.channels.envelope import ChannelMessage, ChannelReply
from glc.config import get_or_create_install_token
from glc.security.adapter_auth import verify_channel_token
from glc.security.allowlists import allowed
from glc.security.pairing import get_pairing_store
from glc.security.rate_limits import get_rate_limiter
from glc.security.trust_level import classify

router = APIRouter()

# In the separated (Part-1 hardened) topology the gateway runs NO adapter code
# in-process: every adapter is its own Modal Function that receives its native
# webhook and relays normalised envelopes over WS /v1/channels/{name}. Running
# `registry.instantiate(name).on_message(...)` inside the gateway is exactly the
# shared-process coupling that makes Leaks 3/5/10 (force_pair_owner, policy
# monkey-patch, log_call poisoning) reachable from adapter code. When
# GLC_INPROC_ADAPTERS is off, the in-gateway webhook handlers refuse to run
# adapter code and point callers at the adapter ingress instead.
def _inproc_adapters_enabled() -> bool:
    return os.getenv("GLC_INPROC_ADAPTERS", "1").strip().lower() not in ("0", "false", "no", "")


@router.websocket("/v1/channels/{name}")
async def channel_ws(websocket: WebSocket, name: str):
    header_auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    presented = None
    if header_auth and header_auth.startswith("Bearer "):
        presented = header_auth.removeprefix("Bearer ").strip()
    install_token = get_or_create_install_token()
    # Accept either the admin/dev install token OR this channel's own scoped
    # token. A channel-scoped token for "telegram" fails this check on route
    # "discord" (different HMAC input), so a compromised adapter can neither
    # authenticate to another channel's route nor to /v1/control/* (which
    # only accepts the raw install token, see glc/routes/control.py) — it
    # never holds anything but its own channel's derived token.
    if presented != install_token and not verify_channel_token(install_token, name, presented):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    state = websocket.app.state
    registered = list(getattr(state, "registered_channels", []))
    if name not in registered:
        registered.append(name)
        state.registered_channels = registered

    limiter = get_rate_limiter()
    pairings = get_pairing_store()
    owners = [p.channel_user_id for p in pairings.owners(channel=name)]

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                env = ChannelMessage.model_validate(payload)
            except Exception as e:
                await websocket.send_text(json.dumps({"error": f"invalid envelope: {e}"}))
                continue

            # Leak 9 — cross-channel envelope spoofing: an adapter (or anything
            # that can reach this socket) could claim env.channel="discord" while
            # connected to WS /v1/channels/telegram. Trust the route, not the
            # envelope; a mismatch is treated as a hard protocol violation, not a
            # droppable message, because it means whatever is on the other end
            # of this socket isn't the adapter it claims to be.
            if env.channel != name:
                audit_append(
                    channel=name,
                    channel_user_id=env.channel_user_id,
                    trust_level=env.trust_level,
                    event_type="envelope_channel_mismatch",
                    result={"route_channel": name, "claimed_channel": env.channel},
                )
                await websocket.send_text(
                    json.dumps(
                        {"error": f"envelope channel {env.channel!r} does not match route channel {name!r}"}
                    )
                )
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

            # Invariant 2 ("checked against the actual user"): the adapter's
            # `env.trust_level` is an unverified claim from an untrusted
            # process — a compromised adapter could just set it to
            # "owner_paired" and every downstream allowlist/policy check
            # would believe it. Re-derive the real trust level from the
            # gateway's own pairing store instead of trusting the envelope;
            # `real_trust` (not `env.trust_level`) is what's used below and
            # is what gets recorded to the audit log.
            real_trust = classify(name, env.channel_user_id)

            ok, why = allowed(
                env.channel,
                env.channel_user_id,
                owner_ids=owners,
                is_public_channel=bool(env.metadata.get("is_public_channel", False)),
                was_mentioned=bool(env.metadata.get("was_mentioned", False)),
            )
            if not ok:
                audit_append(
                    channel=env.channel,
                    channel_user_id=env.channel_user_id,
                    trust_level=real_trust,
                    event_type="allowlist_drop",
                    result={"reason": why},
                )
                await websocket.send_text(json.dumps({"error": f"dropped: {why}"}))
                continue

            ok, why = limiter.check_message(env.channel, env.channel_user_id)
            if not ok:
                audit_append(
                    channel=env.channel,
                    channel_user_id=env.channel_user_id,
                    trust_level=real_trust,
                    event_type="rate_limit",
                    result={"reason": why},
                )
                await websocket.send_text(json.dumps({"status": 429, "error": why}))
                continue

            audit_append(
                channel=env.channel,
                channel_user_id=env.channel_user_id,
                trust_level=real_trust,
                event_type="inbound_message",
                params={"text": env.text, "thread_id": env.thread_id},
            )

            # S11 stub agent: echo the text back so adapter authors can
            # verify the wire end-to-end. The real agent runtime hooks
            # in here in subsequent sessions.
            reply = ChannelReply(
                channel=env.channel,
                channel_user_id=env.channel_user_id,
                text=f"[glc echo] {env.text or ''}",
                thread_id=env.thread_id,
            )
            await websocket.send_text(reply.model_dump_json())
    except WebSocketDisconnect:
        return


@router.get("/v1/channels/{name}/webhook")
async def channel_webhook_verify(name: str, request: Request):
    if not _inproc_adapters_enabled():
        raise HTTPException(
            status_code=410,
            detail="in-gateway adapters disabled; webhooks are served by the separated adapter Function",
        )
    params = dict(request.query_params)
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")
    expected = os.environ.get(f"{name.upper()}_VERIFY_TOKEN", "")
    if mode == "subscribe" and hmac.compare_digest(token, expected):
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403)


@router.post("/v1/channels/{name}/webhook")
async def channel_webhook(name: str, request: Request):
    if not _inproc_adapters_enabled():
        raise HTTPException(
            status_code=410,
            detail="in-gateway adapters disabled; this channel's webhook is served by its own adapter Function",
        )
    try:
        adapter = registry.instantiate(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown channel: {name}") from None

    raw = {
        "raw_body": await request.body(),
        "headers": dict(request.headers),
    }
    msg = await adapter.on_message(raw)
    if msg is None:
        return {"status": "ok"}

    limiter = get_rate_limiter()
    pairings = get_pairing_store()
    owners = [p.channel_user_id for p in pairings.owners(channel=name)]
    # Same re-derivation as the WS path: don't trust msg.trust_level as the
    # adapter computed it, recompute from the gateway's own pairing store.
    real_trust = classify(name, msg.channel_user_id)

    ok, why = allowed(
        msg.channel,
        msg.channel_user_id,
        owner_ids=owners,
        is_public_channel=bool(msg.metadata.get("is_public_channel", False)),
        was_mentioned=bool(msg.metadata.get("was_mentioned", False)),
    )
    if not ok:
        audit_append(
            channel=msg.channel,
            channel_user_id=msg.channel_user_id,
            trust_level=real_trust,
            event_type="allowlist_drop",
            result={"reason": why},
        )
        return {"status": "ok"}

    ok, why = limiter.check_message(msg.channel, msg.channel_user_id)
    if not ok:
        audit_append(
            channel=msg.channel,
            channel_user_id=msg.channel_user_id,
            trust_level=real_trust,
            event_type="rate_limit",
            result={"reason": why},
        )
        return JSONResponse(status_code=429, content={"error": why})

    audit_append(
        channel=msg.channel,
        channel_user_id=msg.channel_user_id,
        trust_level=real_trust,
        event_type="inbound_message",
        params={"text": msg.text, "thread_id": msg.thread_id, "provider": msg.metadata.get("provider")},
    )

    reply = ChannelReply(
        channel=msg.channel,
        channel_user_id=msg.channel_user_id,
        text=f"[glc echo] {msg.text or ''}",
        thread_id=msg.thread_id,
    )
    await adapter.send(reply)
    return {"status": "ok"}
