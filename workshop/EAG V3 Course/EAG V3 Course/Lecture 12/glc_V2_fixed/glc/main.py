"""FastAPI app for glc_v1. Port 8111 by default. V9 routes are mounted
as-is (S9 Browser / S10 Computer-Use clients work unchanged); the new
S11 surfaces (transcribe, speak, channels WS, control) sit alongside.
"""

from __future__ import annotations

import os
import signal
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).parent
load_dotenv(ROOT.parent / ".env")  # repo .env, if present

from glc import db  # noqa: E402
from glc import embedders as E  # noqa: E402
from glc import providers as P  # noqa: E402
from glc.audit import init_store as init_audit  # noqa: E402
from glc.cache import GeminiCache  # noqa: E402
from glc.config import get_or_create_install_token  # noqa: E402
from glc.policy import reload_engine  # noqa: E402
from glc.routes import channels as channels_route  # noqa: E402
from glc.routes import chat as chat_route  # noqa: E402
from glc.routes import control as control_route  # noqa: E402
from glc.routes import speak as speak_route  # noqa: E402
from glc.routes import transcribe as transcribe_route  # noqa: E402
from glc.routing import Router, RouterPool  # noqa: E402
from glc.security.auth import require_bearer_token  # noqa: E402
from glc.security.data_plane_limits import enforce_cost_budget, enforce_rate_limit  # noqa: E402

PORT = int(os.getenv("GLC_PORT", "8111"))

# A2 — /docs, /redoc and /openapi.json currently leak the full route map,
# provider order, models, and rate limits to anyone. Off by default in
# production (GLC_ENV=production, set by the deployed gateway image in
# modal_app.py); left on for local dev so `modal serve` / `uvicorn --reload`
# still get the explorer.
_PRODUCTION = os.getenv("GLC_ENV", "development").strip().lower() == "production"


def _install_sighup_reload() -> None:
    """Hot-reload policy.yaml on SIGHUP. Windows lacks SIGHUP so this is
    a no-op there."""
    if not hasattr(signal, "SIGHUP"):
        return

    def _handler(signum, frame):  # noqa: ARG001
        try:
            reload_engine()
            print("[glc] policy.yaml reloaded via SIGHUP")
        except Exception as e:
            print(f"[glc] SIGHUP reload failed: {e!r}")

    try:
        signal.signal(signal.SIGHUP, _handler)
    except ValueError:
        # signal() only works on the main thread; tests using TestClient
        # spawn lifespan from a worker thread. Silent skip is correct here.
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    init_audit()
    get_or_create_install_token()
    _install_sighup_reload()
    app.state.cache = GeminiCache(ttl_seconds=300)
    app.state.providers = P.build_providers(app.state.cache)
    app.state.router = Router(app.state.providers, chat_route.ORDER)
    app.state.router_providers = P.build_router_providers()
    app.state.router_pool = RouterPool(app.state.router_providers, chat_route.ROUTER_ORDER)
    app.state.embedders, app.state.embed_order = E.build_embedders()
    app.state.started_at = time.time()
    app.state.registered_channels = []
    yield


app = FastAPI(
    title="GLC v1 — Gateway for LLMs and Channels",
    lifespan=lifespan,
    docs_url=None if _PRODUCTION else "/docs",
    redoc_url=None if _PRODUCTION else "/redoc",
    openapi_url=None if _PRODUCTION else "/openapi.json",
)

# A1/A2 — every /v1/* data-plane and info-disclosure route requires the
# install token. Applied once per router at include_router() time (not per
# endpoint) so a route added to chat.py/speak.py/transcribe.py later can't be
# left un-gated by accident. control_route already carries the same
# dependency on its own APIRouter (glc/routes/control.py). channels_route is
# deliberately NOT blanket-gated here: its WS route authenticates the same
# way itself (see channels.py), but its GET/POST .../webhook routes are
# called by the external channel provider (e.g. Meta), which cannot present
# our bearer token — those use their own hub.verify_token scheme instead,
# and are further gated by GLC_INPROC_ADAPTERS in the separated topology.
# C5 — rate limit + cost circuit breaker on the data plane, applied after
# auth (an unauthenticated caller never even reaches the limiter) and at
# router-include time, same "no un-gated route by accident" reasoning as
# require_bearer_token above.
_v1_auth = [
    Depends(require_bearer_token),
    Depends(enforce_rate_limit),
    Depends(enforce_cost_budget),
]
app.include_router(chat_route.router, dependencies=_v1_auth)
app.include_router(transcribe_route.router, dependencies=_v1_auth)
app.include_router(speak_route.router, dependencies=_v1_auth)
app.include_router(control_route.router)
app.include_router(channels_route.router)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (
        "<html><body style='font-family:sans-serif;max-width:680px;margin:2em auto'>"
        "<h1>GLC v1</h1>"
        "<p>Gateway for LLMs and Channels — Session 11 scaffold.</p>"
        "<p>Open <code>/docs</code> for the OpenAPI explorer.</p>"
        "<p>Channel adapters connect over <code>WS /v1/channels/&lt;name&gt;</code>."
        " V9 callers should point at this port unchanged: chat, vision, embed,"
        " batch, cost-by-agent, providers, capabilities, status, calls."
        "</p>"
        "</body></html>"
    )


@app.get("/healthz")
async def healthz():
    return {"ok": True, "port": PORT}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("glc.main:app", host="0.0.0.0", port=PORT, reload=False)
