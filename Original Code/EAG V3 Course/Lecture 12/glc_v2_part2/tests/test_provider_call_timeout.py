"""Invariant 8 ("every run has hard limits on time, tokens, tool calls,
cost") -- /v1/chat has no wall-clock ceiling on the actual provider call,
in either the non-streaming or streaming path. A provider whose chat()/
stream() call stalls (dead connection, buggy SDK, a slow or compromised
upstream) blocks the request indefinitely: nothing in glc/routes/chat.py
wraps `await provider.chat(...)` or the `async for chunk in
provider.stream(...)` loop in any timeout. The existing retry logic only
ever fires when the provider *raises*; an await that simply never
resolves never reaches it.

This is not one of the Section 6/7 findings -- "timeout" and "hang" do
not appear anywhere in that list. Reproduced here against a fresh
checkout with no live provider keys and no deployment: a fake provider
stands in for a stalled upstream, and the test proves the server takes
as long as the stall (bug) rather than being bounded by a configured
ceiling (fix).
"""

from __future__ import annotations

import asyncio
import time


class _SlowChatProvider:
    model = "fake-slow-model"
    capabilities: dict = {}

    async def chat(self, *args, **kwargs):
        await asyncio.sleep(0.3)
        return {
            "text": "too-late",
            "model": self.model,
            "tool_calls": [],
            "stop_reason": "end_turn",
            "input_tokens": 1,
            "output_tokens": 1,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "tool_call_dialect": "none",
            "reasoning_applied": False,
        }


class _SlowStreamProvider:
    model = "fake-slow-stream-model"
    capabilities: dict = {}

    async def stream(self, *args, **kwargs):
        await asyncio.sleep(0.3)
        yield "too-late"


def test_chat_is_not_bounded_by_any_wall_clock_timeout(app_client, monkeypatch):
    """Before the fix: no GLC_PROVIDER_TIMEOUT_SECONDS exists at all, so a
    provider that takes 0.3s always takes the full 0.3s -- there is no
    ceiling to configure. After the fix: setting the ceiling below the
    provider's stall time returns well before it, converted into the
    existing retry/error handling instead of an unbounded wait."""
    monkeypatch.setenv("GLC_PROVIDER_TIMEOUT_SECONDS", "0.05")
    app_client.app.state.router.providers["gemini"] = _SlowChatProvider()

    t0 = time.time()
    r = app_client.post("/v1/chat", json={"prompt": "hi", "provider": "gemini"})
    elapsed = time.time() - t0

    assert elapsed < 0.2, f"provider.chat() was not bounded by any timeout (took {elapsed:.3f}s)"
    assert r.status_code in (502, 503)
    assert "too-late" not in r.text


def test_streaming_chat_is_not_bounded_by_any_wall_clock_timeout(app_client, monkeypatch):
    monkeypatch.setenv("GLC_PROVIDER_TIMEOUT_SECONDS", "0.05")
    app_client.app.state.router.providers["gemini"] = _SlowStreamProvider()

    t0 = time.time()
    r = app_client.post(
        "/v1/chat",
        json={"prompt": "hi", "provider": "gemini", "stream": True},
    )
    elapsed = time.time() - t0

    assert elapsed < 0.2, f"provider.stream() was not bounded by any timeout (took {elapsed:.3f}s)"
    assert "too-late" not in r.text
    assert '"done": true' not in r.text
    assert "time limit" in r.text
