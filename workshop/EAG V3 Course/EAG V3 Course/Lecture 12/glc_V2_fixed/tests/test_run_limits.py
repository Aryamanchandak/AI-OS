"""Invariant 8 — hard per-run limits on time, tokens, tool calls, and cost.

Before this, /v1/chat had a per-caller requests-per-minute bucket and a
gateway-wide DAILY cost ceiling (see glc/security/data_plane_limits.py),
but nothing bounded a single run's own token count, wall-clock execution
time, or its own estimated cost -- and BatchChatRequest's fan-out
(`calls` length, `max_concurrency`) was similarly unbounded. These tests
cover the four additions: max_tokens ceiling, batch size/concurrency
ceilings, a per-run wall-clock timeout, and a per-run cost ceiling.
"""

from __future__ import annotations

import asyncio
import time


def test_chat_rejects_max_tokens_over_ceiling(app_client, install_token, monkeypatch):
    monkeypatch.setenv("GLC_MAX_TOKENS_CEILING", "100")
    r = app_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"prompt": "hi", "max_tokens": 999999},
    )
    assert r.status_code == 422
    assert "exceeds the per-run ceiling" in r.text


def test_chat_accepts_max_tokens_at_ceiling(app_client, install_token, monkeypatch):
    monkeypatch.setenv("GLC_MAX_TOKENS_CEILING", "100")
    r = app_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"prompt": "hi", "max_tokens": 100, "provider": "gemini"},
    )
    # Whatever happens downstream (real fake providers aren't configured in
    # tests), it must not be rejected by the max_tokens validator itself.
    assert r.status_code != 422


def test_batch_rejects_too_many_calls(app_client, install_token, monkeypatch):
    monkeypatch.setenv("GLC_MAX_BATCH_CALLS", "2")
    r = app_client.post(
        "/v1/chat/batch",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"calls": [{"prompt": "a"}, {"prompt": "b"}, {"prompt": "c"}]},
    )
    assert r.status_code == 422
    assert "exceeds the per-run limit" in r.text


def test_batch_rejects_excess_concurrency(app_client, install_token, monkeypatch):
    monkeypatch.setenv("GLC_MAX_BATCH_CONCURRENCY", "4")
    r = app_client.post(
        "/v1/chat/batch",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"calls": [{"prompt": "a"}], "max_concurrency": 999},
    )
    assert r.status_code == 422
    assert "exceeds the per-run limit" in r.text


class _HangingProvider:
    model = "fake-hanging-model"
    capabilities: dict = {}

    async def chat(self, *args, **kwargs):
        await asyncio.sleep(999)


def test_chat_run_times_out_on_a_hanging_provider(app_client, install_token, monkeypatch):
    """Before this fix, a provider call that simply never returned (no
    exception, no timeout) blocked the request forever -- nothing in the
    request path bounded wall-clock execution time."""
    monkeypatch.setenv("GLC_RUN_TIMEOUT_SECONDS", "0.05")
    app_client.app.state.router.providers["gemini"] = _HangingProvider()

    r = app_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"prompt": "hi", "provider": "gemini"},
    )
    assert r.status_code == 504
    assert "execution-time limit" in r.text


class _InstantProvider:
    model = "fake-instant-model"
    capabilities: dict = {}

    async def chat(self, *args, **kwargs):
        return {
            "text": "ok",
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


def test_chat_run_completes_normally_within_the_timeout(app_client, install_token, monkeypatch):
    monkeypatch.setenv("GLC_RUN_TIMEOUT_SECONDS", "30")
    app_client.app.state.router.providers["gemini"] = _InstantProvider()

    r = app_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"prompt": "hi", "provider": "gemini"},
    )
    assert r.status_code == 200
    assert r.json()["text"] == "ok"


def test_chat_rejects_run_whose_worst_case_cost_exceeds_the_per_run_ceiling(
    app_client, install_token, monkeypatch
):
    monkeypatch.setenv("GLC_PER_RUN_COST_CEILING_USD", "0.0001")
    monkeypatch.setenv("GLC_MAX_TOKENS_CEILING", "999999")
    r = app_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"prompt": "hi " * 500, "max_tokens": 100000},
    )
    assert r.status_code == 413
    assert "per-run ceiling" in r.text


def test_chat_per_run_cost_ceiling_disabled_at_zero(app_client, install_token, monkeypatch):
    monkeypatch.setenv("GLC_PER_RUN_COST_CEILING_USD", "0")
    app_client.app.state.router.providers["gemini"] = _InstantProvider()
    r = app_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"prompt": "hi", "provider": "gemini"},
    )
    assert r.status_code == 200


class _SlowStreamProvider:
    """A stream() that sleeps past the run timeout before its first yield --
    the shape of a hung/slow upstream provider on the streaming path."""

    model = "fake-slow-stream-model"
    capabilities: dict = {}

    async def stream(self, *args, **kwargs):
        await asyncio.sleep(0.3)
        yield "too-late"


def test_streaming_chat_run_times_out_on_a_hanging_provider(app_client, install_token, monkeypatch):
    """Invariant 8 (Part 2 candidate): the timeout wrapper in `chat()` is
    `wait_for(_chat_impl(req, request), timeout=...)`. For stream=true,
    `_chat_impl` returns a `StreamingResponse(gen(), ...)` object *before*
    `gen()`'s body -- the actual provider.stream() call -- ever runs, so
    `wait_for` is satisfied instantly and bounds nothing on the streaming
    path. A provider whose stream() hangs (or is simply slow) can hold the
    connection open past the configured run timeout indefinitely; on the
    A6-pinned single gateway container this is a whole-gateway DoS, not
    just a slow response to one caller.

    Before the fix: this request takes >= 0.3s (the full artificial delay)
    and its body contains the "too-late" chunk and a normal "done" frame --
    proof the run timeout was never applied to the stream body.
    After the fix: the request returns well under 0.3s with a
    run-timeout error frame in the body and no "too-late"/"done" content.
    """
    monkeypatch.setenv("GLC_RUN_TIMEOUT_SECONDS", "0.05")
    app_client.app.state.router.providers["gemini"] = _SlowStreamProvider()

    t0 = time.time()
    r = app_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"prompt": "hi", "provider": "gemini", "stream": True},
    )
    elapsed = time.time() - t0

    assert elapsed < 0.2, f"stream was not bounded by the run timeout (took {elapsed:.3f}s)"
    assert "too-late" not in r.text
    assert '"done": true' not in r.text
    assert "execution-time limit" in r.text
