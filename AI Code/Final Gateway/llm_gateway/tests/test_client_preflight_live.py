"""Real (non-mocked) test for LLM.preflight() against an actually-running
gateway. test_client_preflight.py only stubs chat()/embed(), so it can't
catch a bad prompt/schema pairing that fails against a real model but passes
every unit test — this is the honest check for that class of bug.

Spins up main:app with uvicorn on a free localhost port in a background
thread (client.py makes real httpx calls to a base_url, it has no injectable
transport), points a real LLM client at it, and calls preflight() for real.
Requires local Ollama + at least one real chat provider configured — same
prerequisites as tests/test_embed.py's `local` marker.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from contextlib import closing
from pathlib import Path

import pytest
from dotenv import load_dotenv

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
load_dotenv(HERE.parent / ".env")

from client import LLM, GatewayPreflightError


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_gateway():
    import uvicorn
    import main as M

    port = _free_port()
    config = uvicorn.Config(M.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.1)
    assert server.started, "gateway did not start within 15s"

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.local
@pytest.mark.network
def test_preflight_succeeds_against_a_real_gateway(live_gateway):
    """Pins chat_provider away from the gateway's default first choice
    (`gemma`, a small local model) — see the gotcha note below on why that
    default is a bad fit for a deterministic assertion, independent of
    whether the gateway is actually healthy. Needs a real hosted provider
    for the chat leg (here `gemini-flash`), so it's also `network`-marked —
    same category as test_embed.py's existing network tests, and subject to
    the same real-world flakiness (e.g. an IP-restricted API key)."""
    llm = LLM(base_url=live_gateway)
    checks = llm.preflight(embedding_profile="chunker-v1", chat_provider="gemini-flash")
    assert checks["chat"]["ok"] is True, checks
    assert checks["embedding"]["ok"] is True, checks
    assert checks["embedding"]["model"] == "nomic-embed-text"
    assert checks["embedding"]["dim"] == 768


@pytest.mark.local
def test_preflight_reports_embedding_failure_for_unknown_profile(live_gateway, monkeypatch):
    """Isolates the embedding-failure path from the chat path over a real
    HTTP call. `chat()` is stubbed here (not the point of this test — see
    the gotcha note below); `embed()` still makes a real request."""
    llm = LLM(base_url=live_gateway)
    monkeypatch.setattr(llm, "chat", lambda *a, **kw: {"provider": "stub", "model": "stub"})
    with pytest.raises(GatewayPreflightError) as exc_info:
        llm.preflight(embedding_profile="no-such-profile")
    assert exc_info.value.checks["chat"]["ok"] is True
    assert exc_info.value.checks["embedding"]["ok"] is False


# Gotchas found while writing this test (both fixed in client.py's
# preflight() prompt, not papered over here):
#
# 1. `max_tokens` too low + a reasoning-capable model = truncated JSON.
#    gemini-2.5-flash (gemini-flash's model) spends output-token budget on
#    invisible "thinking" before the visible answer; at max_tokens=64 it
#    would sometimes burn the whole budget mid-thought and truncate
#    `{"ok": true}` to `{"ok":` (stop_reason="max_tokens"), which fails JSON
#    schema validation even though the gateway and model are both healthy.
#    Fixed by passing `reasoning="off"` and raising max_tokens to 256 — 10/10
#    clean structured completions in a row after that change (was ~intermittent
#    before, isolated via direct provider.chat() calls bypassing the gateway).
#
# 2. The gateway's default provider order tries `gemma` (local, small model)
#    first for chat with no pinned provider. `main.py` makes one fix-up retry
#    when structured output fails schema validation, then raises a real 503
#    (main.py:~275) — a small local model can fail even a trivial strict-JSON
#    schema on both the original and fix-up attempt. Production
#    `GatewayExtractor` calls also don't pin a provider, so real extraction
#    runs inherit the same intermittent failure mode from `gemma`. If a
#    caller wants preflight() to gate on a provider whose structured-output
#    reliability has actually been validated, pass `chat_provider=` (e.g. a
#    hosted provider) rather than relying on the gateway's default order —
#    that's why the positive test above pins `chat_provider="gemini-flash"`.
#
# A residual, *irreducible* source of flakiness remains: real upstream
# `503 UNAVAILABLE` from Google's Gemini API itself, seen directly against
# the provider outside the gateway. That's genuine transient cloud-provider
# unavailability, not a bug — a real preflight() run hitting it is preflight
# doing its job (the gateway currently can't serve that provider).
