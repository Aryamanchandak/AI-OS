"""Bearer-token auth dependency for the gateway's HTTP surface.

Part 1 hardening (A1/A2): before this module, `/v1/chat`, `/v1/vision`,
`/v1/embed`, `/v1/speak`, `/v1/transcribe` and the info-disclosure routes
(`/v1/status`, `/v1/providers`, `/v1/capabilities`, `/v1/cost/by_agent`,
`/v1/calls`, `/v1/embedders`, `/v1/routers`) ran for anyone with the URL —
no credential of any kind. `glc/routes/control.py` already gated its own
routes with a hand-rolled bearer check against the install token; this
module is that same check, extracted so every other `/v1/*` router can
require it too via `dependencies=[Depends(require_bearer_token)]` at
`include_router()` time — enforced once per router, not per endpoint, so a
new route added to an already-gated router can't be added un-gated by
accident.

Reuses the existing install token (`glc.config.get_or_create_install_token`)
rather than introducing a second credential type: it is already the single
"is this caller legitimate" secret shared between the control plane and the
adapter WS, and this gateway has no per-caller roles/scopes for a second
token type to usefully distinguish.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from glc.config import get_or_create_install_token


def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    expected = get_or_create_install_token()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token (Authorization: Bearer <token>)")
    presented = authorization.removeprefix("Bearer ").strip()
    if presented != expected:
        raise HTTPException(403, "token mismatch")
