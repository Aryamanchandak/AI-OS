"""Authenticated channel, webhook, WebSocket, and administration routes."""

from __future__ import annotations

import hmac
import json
import os
from typing import Annotated, Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from gateway.app.dependencies import get_channel_service, get_control_service
from gateway.app.router_registry import RouterRegistration
from gateway.channels import setup
from gateway.channels.agent_bridge import AgentBridgeError
from gateway.channels.envelope import ChannelMessage
from gateway.channels.service import ChannelDisabledError, ChannelService
from gateway.control import ControlService

router = APIRouter()


class ChannelSettingsUpdate(BaseModel):
    enabled: bool | None = None
    values: dict[str, str] = Field(default_factory=dict)


def _disabled(error: ChannelDisabledError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(error))


async def _dispatch(service: ChannelService, adapter: Any, message: ChannelMessage | None) -> dict[str, str]:
    if message is None:
        return {"status": "ok"}
    try:
        reply = await service.handle(message)
    except ChannelDisabledError as exc:
        raise _disabled(exc) from exc
    except AgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if reply is not None:
        await adapter.send(reply)
    return {"status": "ok"}


@router.websocket("/v1/channels/{name}")
async def channel_ws(
    websocket: WebSocket,
    name: str,
    token: str | None = Query(default=None),
) -> None:
    service: ChannelService = websocket.app.state.container.channels
    presented = (websocket.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    presented = presented or (token or "")
    expected = websocket.app.state.container.control.install_token
    if not presented or not hmac.compare_digest(presented, expected):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        service.require_enabled(name)
    except ChannelDisabledError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="channel disabled")
        return
    await websocket.accept()
    service.connected.add(name)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = ChannelMessage.model_validate_json(raw)
                if message.channel != name:
                    raise ValueError("envelope channel does not match route")
                reply = await service.handle(message)
                if reply is None:
                    await websocket.send_json({"status": "dropped"})
                else:
                    await websocket.send_text(reply.model_dump_json())
            except (ValueError, json.JSONDecodeError) as exc:
                await websocket.send_json({"error": f"invalid envelope: {exc}"})
            except AgentBridgeError as exc:
                await websocket.send_json({"status": 503, "error": str(exc)})
    except WebSocketDisconnect:
        pass
    finally:
        service.connected.discard(name)


@router.post("/webhooks/twilio_sms")
async def twilio_sms_webhook(
    request: Request,
    service: Annotated[ChannelService, Depends(get_channel_service)],
) -> Response:
    from gateway.channels.catalogue.twilio_sms.webhook import validate_signature

    try:
        adapter = service.instantiate("twilio_sms")
    except ChannelDisabledError as exc:
        raise _disabled(exc) from exc
    body = (await request.body()).decode("utf-8")
    form = dict(parse_qsl(body, keep_blank_values=True))
    valid = validate_signature(
        os.getenv("TWILIO_AUTH_TOKEN", ""), str(request.url), form,
        request.headers.get("X-Twilio-Signature"),
    )
    if not valid:
        return Response(status_code=403, content="invalid signature")
    await _dispatch(service, adapter, await adapter.on_message(form))
    return Response(
        status_code=200, media_type="application/xml",
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
    )


@router.get("/v1/channels/{name}/webhook")
async def channel_webhook_verify(
    name: str,
    request: Request,
    service: Annotated[ChannelService, Depends(get_channel_service)],
) -> PlainTextResponse:
    try:
        service.require_enabled(name)
    except ChannelDisabledError as exc:
        raise _disabled(exc) from exc
    if setup.CHANNEL_SPECS.get(name, {}).get("verification") != "meta_hub":
        raise HTTPException(status_code=404, detail="this channel has no native verification")
    params = request.query_params
    expected = os.getenv(f"{name.upper()}_VERIFY_TOKEN", "")
    if params.get("hub.mode") == "subscribe" and hmac.compare_digest(params.get("hub.verify_token", ""), expected):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="verification failed")


@router.post("/v1/channels/{name}/webhook")
async def channel_webhook(
    name: str,
    request: Request,
    service: Annotated[ChannelService, Depends(get_channel_service)],
) -> dict[str, str]:
    if not setup.CHANNEL_SPECS.get(name, {}).get("webhook", False):
        raise HTTPException(status_code=404, detail="this channel has no native webhook ingress")
    try:
        adapter = service.instantiate(name)
    except ChannelDisabledError as exc:
        raise _disabled(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raw = {"raw_body": await request.body(), "headers": dict(request.headers)}
    return await _dispatch(service, adapter, await adapter.on_message(raw))


@router.get("/v1/channels")
async def channel_catalogue(
    service: Annotated[ChannelService, Depends(get_channel_service)],
) -> dict[str, object]:
    return {
        "channels": [
            {**item, "connected": item["name"] in service.connected}
            for item in service.presence() if item["kind"] == "channel"
        ]
    }


def _admin(
    control: ControlService,
    authorization: str | None,
) -> None:
    control.authenticate(authorization)


@router.get("/v1/channel-admin/catalogue")
async def channel_admin_catalogue(
    request: Request,
    service: Annotated[ChannelService, Depends(get_channel_service)],
    control: Annotated[ControlService, Depends(get_control_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _admin(control, authorization)
    base = os.getenv("GLC_PUBLIC_BASE", str(request.base_url).rstrip("/"))
    names = [item["name"] for item in service.presence() if item["kind"] == "channel"]
    return {"channels": setup.public_catalogue(base, [str(name) for name in names])}


@router.put("/v1/channel-admin/{name}")
async def update_channel_settings(
    name: str,
    settings: ChannelSettingsUpdate,
    service: Annotated[ChannelService, Depends(get_channel_service)],
    control: Annotated[ControlService, Depends(get_control_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    _admin(control, authorization)
    known = {item["name"] for item in service.presence() if item["kind"] == "channel"}
    if name not in setup.CHANNEL_SPECS or name not in known:
        raise HTTPException(status_code=404, detail=f"unknown channel: {name}")
    control.require_audit_writable()
    setup.update(name, settings.values, settings.enabled)
    if settings.enabled is not None:
        service.set_enabled(name, settings.enabled)
    if settings.enabled:
        setup.apply_saved_environment()
    control.audit_control("channel_configuration_updated", params={"channel": name, "enabled": settings.enabled})
    return {"status": "saved"}


def registration() -> RouterRegistration:
    return RouterRegistration(router=router, prefix="", tags=("channels",))
