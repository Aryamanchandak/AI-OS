from __future__ import annotations

import os
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from gateway.app.dependencies import get_control_service
from gateway.control.service import ControlService
from gateway.security.pairing import CODE_TTL_SECONDS
from gateway.app.router_registry import RouterRegistration

router = APIRouter()


class PairRequest(BaseModel):
    channel: str
    channel_user_id: str
    user_handle: str = ""
    trust_level: str = "user_paired"


class PairResponse(BaseModel):
    code: str
    expires_at: float
    ttl_seconds: int


class PairConfirmRequest(BaseModel):
    code: str


def _authorized(
    service: Annotated[ControlService, Depends(get_control_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> ControlService:
    service.authenticate(authorization)
    return service


@router.post("/v1/control/pair", response_model=PairResponse)
def pair(request: PairRequest, service: Annotated[ControlService, Depends(_authorized)]) -> PairResponse:
    if request.trust_level not in ("user_paired", "owner_paired"):
        raise HTTPException(
            400,
            f"trust_level must be user_paired or owner_paired, got {request.trust_level!r}",
        )
    code, expires_at = service.pairings.issue_code(
        request.channel,
        request.channel_user_id,
        request.user_handle,
        requested_trust_level=request.trust_level,
    )
    service.audit_control(
        "pairing_code_issued",
        params={"channel": request.channel, "channel_user_id": request.channel_user_id},
    )
    return PairResponse(code=code, expires_at=expires_at, ttl_seconds=CODE_TTL_SECONDS)


@router.post("/v1/control/pair/confirm", response_model=None)
def pair_confirm(
    request: PairConfirmRequest,
    service: Annotated[ControlService, Depends(_authorized)],
) -> Any:
    record = service.pairings.confirm_code(request.code)
    if record is None:
        raise HTTPException(404, "code unknown or expired")
    result: dict[str, object] = {
        "channel": record.channel,
        "channel_user_id": record.channel_user_id,
        "user_handle": record.user_handle,
        "trust_level": record.trust_level,
        "paired_at": record.paired_at,
    }
    service.audit_control("pairing_confirmed", result=result)
    return result


@router.get("/v1/control/presence", response_model=None)
def presence(service: Annotated[ControlService, Depends(_authorized)]) -> Any:
    paired_users = [
        {
            "channel": item.channel,
            "channel_user_id": item.channel_user_id,
            "user_handle": item.user_handle,
            "trust_level": item.trust_level,
        }
        for item in service.pairings.all_pairings()
    ]
    result: dict[str, object] = {
        "channels": [],
        "paired_users": paired_users,
        "uptime_s": int(time.time() - service.started_at),
    }
    service.audit_control("presence_read", result={"paired_user_count": len(paired_users)})
    return result


@router.post("/v1/control/reload-policy")
def reload_policy(service: Annotated[ControlService, Depends(_authorized)]) -> dict[str, str]:
    service.reload_policy(trigger="http")
    return {"status": "reloaded"}


@router.post("/v1/control/kill", response_model=None)
def kill(
    request: Request,
    service: Annotated[ControlService, Depends(_authorized)],
) -> Any:
    client_host = request.client.host if request.client else "unknown"
    if os.getenv("GLC_KILL_ALLOW_REMOTE") != "1" and client_host not in (
        "127.0.0.1", "::1", "localhost"
    ):
        raise HTTPException(
            403,
            f"kill is restricted to loopback (got {client_host}). "
            "Set GLC_KILL_ALLOW_REMOTE=1 to override (not recommended).",
        )
    return service.suspend_glc()


def registration() -> RouterRegistration:
    return RouterRegistration(router=router, prefix="", tags=())
