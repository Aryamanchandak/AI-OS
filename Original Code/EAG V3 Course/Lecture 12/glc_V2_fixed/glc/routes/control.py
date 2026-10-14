"""Out-of-band control plane: /v1/control/kill, /v1/control/pair,
/v1/control/pair/confirm, /v1/control/presence.

All endpoints require the installation token (Authorization: Bearer ...),
enforced once at the router level via `glc.security.auth.require_bearer_token`
rather than per-route (see that module — same dependency now also gates the
/v1/* data-plane and info-disclosure routes in chat.py/speak.py/transcribe.py,
Phase 4 A1/A2). The kill endpoint additionally binds 127.0.0.1 only; that
host check is route-specific and stays here.
"""

from __future__ import annotations

import os
import signal
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from glc.audit.store import verify_chain
from glc.security.auth import require_bearer_token
from glc.security.pairing import CODE_TTL_SECONDS, get_pairing_store

router = APIRouter(dependencies=[Depends(require_bearer_token)])


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


@router.post("/v1/control/pair", response_model=PairResponse)
async def pair(req: PairRequest):
    # Phase 7 (Leak 3/10 narrowing): the HTTP pairing endpoint may only ever
    # grant `user_paired`. `owner_paired` is the installation's single most
    # privileged trust level (policy.yaml default-allows it), and it must NOT
    # be mintable through a self-service HTTP request — even by a raw
    # install-token holder. Owner identity is bootstrapped exactly once,
    # out-of-band, by the installer via PairingStore.force_pair_owner(); there
    # is deliberately no HTTP path that produces it. This removes the
    # "hold the token -> POST trust_level=owner_paired -> self-confirm ->
    # owner" escalation shape entirely, rather than relying on the token
    # holder being trusted.
    if req.trust_level != "user_paired":
        raise HTTPException(
            400,
            f"trust_level must be 'user_paired' (got {req.trust_level!r}); "
            "owner_paired is bootstrapped out-of-band by the installer, never over HTTP",
        )
    code, expires_at = get_pairing_store().issue_code(
        req.channel,
        req.channel_user_id,
        req.user_handle,
        requested_trust_level=req.trust_level,
    )
    return PairResponse(code=code, expires_at=expires_at, ttl_seconds=CODE_TTL_SECONDS)


@router.post("/v1/control/pair/confirm")
async def pair_confirm(req: PairConfirmRequest):
    rec = get_pairing_store().confirm_code(req.code)
    if rec is None:
        raise HTTPException(404, "code unknown or expired")
    return {
        "channel": rec.channel,
        "channel_user_id": rec.channel_user_id,
        "user_handle": rec.user_handle,
        "trust_level": rec.trust_level,
        "paired_at": rec.paired_at,
    }


@router.get("/v1/control/presence")
async def presence(request: Request):
    state = request.app.state
    started = getattr(state, "started_at", time.time())
    pairings = get_pairing_store().all_pairings()
    return {
        "channels": getattr(state, "registered_channels", []),
        "paired_users": [
            {
                "channel": p.channel,
                "channel_user_id": p.channel_user_id,
                "user_handle": p.user_handle,
                "trust_level": p.trust_level,
            }
            for p in pairings
        ],
        "uptime_s": int(time.time() - started),
    }


@router.get("/v1/control/audit/verify")
async def audit_verify():
    """Invariant 7 (append-only audit log): run the hash-chain + checkpoint
    verification on demand. verify_chain() already runs automatically at
    gateway startup (see glc/audit/store.py::init_store) and logs+records
    a failure there; this route lets an operator check it at any time
    without needing gateway-process code execution."""
    return verify_chain()


@router.post("/v1/control/kill")
async def kill(request: Request):
    client_host = request.client.host if request.client else "unknown"
    if os.getenv("GLC_KILL_ALLOW_REMOTE") != "1" and client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            403,
            f"kill is restricted to loopback (got {client_host}). "
            "Set GLC_KILL_ALLOW_REMOTE=1 to override (not recommended).",
        )
    # Send SIGTERM to ourselves shortly after returning so the client gets a 200.
    import asyncio

    async def _shoot() -> None:
        await asyncio.sleep(0.2)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_shoot())
    return {"status": "terminating", "pid": os.getpid()}
