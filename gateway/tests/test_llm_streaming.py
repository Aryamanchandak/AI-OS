"""Streaming chat path — SSE frame shape and stage-9 ordering.

The frames these tests assert are the ones `glc_v5/glc/routes/chat.py:826-933`
emits. Key *order* is part of the contract because `json.dumps` preserves
insertion order and callers parse the raw bytes.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException
import pytest

from gateway.llm.models import ChatRequest
from gateway.llm.providers.base import (
    TOOL_CALL_DELTA, ProviderCapabilities, ProviderError, ProviderResult, ProviderUsage,
    fallback_stream,
)
from gateway.llm.cache import SemanticCache, SemanticCacheConfig
from gateway.llm.economics import BudgetController, PricingTable
from gateway.llm.profiles import ProfileRegistry

from test_llm import AuditSpy, FakeProvider, budget_files, service_for


class BufferedProvider(FakeProvider):
    """Streams the way every non-OpenAI-compatible provider does: one frame,
    with the vendor's resolved model published through the sink."""

    def __init__(self, name: str, *, text: str = "hello", model: str | None = None) -> None:
        super().__init__(name)
        self.text = text
        if model is not None:
            self.model = model

    async def chat(self, **kwargs: Any) -> ProviderResult:
        self.calls += 1
        return ProviderResult(provider=self.name, model=self.model, text=self.text,
                              usage=ProviderUsage(10, 2))

    def stream(self, **kwargs: Any):
        return fallback_stream(self.chat, **kwargs)


class IncrementalProvider(FakeProvider):
    """Streams the way the OpenAI-compatible family does: many text chunks,
    tool-call deltas behind the marker, model confirmed mid-stream."""

    capabilities = ProviderCapabilities()

    def __init__(self, name: str, chunks: list[str], *, confirm_model: bool = True) -> None:
        super().__init__(name)
        self.chunks = chunks
        self.confirm_model = confirm_model

    async def stream(self, *, result_sink: dict[str, Any] | None = None, **kwargs: Any):
        for chunk in self.chunks:
            if result_sink is not None and self.confirm_model:
                result_sink["model"] = self.model
            yield chunk


class ExplodingProvider(FakeProvider):
    async def stream(self, *, result_sink: dict[str, Any] | None = None, **kwargs: Any):
        yield "partial"
        raise ProviderError("upstream died mid-stream")


def frames(service: Any, request: ChatRequest) -> list[dict[str, Any]]:
    async def collect() -> list[dict[str, Any]]:
        generator = await service.stream_chat(request)
        out = []
        async for frame in generator:
            assert frame.startswith("data: ") and frame.endswith("\n\n")
            out.append(json.loads(frame[6:-2]))
        return out

    return asyncio.run(collect())


def test_buffered_provider_streams_one_delta_then_done(tmp_path: Path) -> None:
    service, _ = service_for(tmp_path, [BufferedProvider("solo", text="hello world")])
    result = frames(service, ChatRequest(prompt="hi", stream=True))
    assert result == [
        {"provider": "solo", "delta": "hello world"},
        {"done": True, "provider": "solo", "model": "solo-model", "profile": None},
    ]


def test_done_frame_key_order_matches_legacy(tmp_path: Path) -> None:
    service, _ = service_for(tmp_path, [BufferedProvider("solo")])
    async def collect() -> list[str]:
        return [frame async for frame in await service.stream_chat(ChatRequest(prompt="hi", stream=True))]
    raw = asyncio.run(collect())
    assert raw[-1] == 'data: {"done": true, "provider": "solo", "model": "solo-model", "profile": null}\n\n'


def test_empty_text_emits_no_delta_frame(tmp_path: Path) -> None:
    service, _ = service_for(tmp_path, [BufferedProvider("solo", text="")])
    result = frames(service, ChatRequest(prompt="hi", stream=True))
    assert result == [{"done": True, "provider": "solo", "model": "solo-model", "profile": None}]


def test_incremental_provider_emits_one_frame_per_chunk(tmp_path: Path) -> None:
    provider = IncrementalProvider("inc", ["Hel", "lo ", "there"])
    service, _ = service_for(tmp_path, [provider])
    result = frames(service, ChatRequest(prompt="hi", stream=True))
    assert [x.get("delta") for x in result[:-1]] == ["Hel", "lo ", "there"]
    assert result[-1]["done"] is True


def test_tool_call_deltas_use_their_own_frame_key(tmp_path: Path) -> None:
    payload = json.dumps([{"index": 0, "function": {"name": "lookup"}}])
    provider = IncrementalProvider("inc", ["thinking", f"{TOOL_CALL_DELTA} {payload}"])
    service, _ = service_for(tmp_path, [provider])
    result = frames(service, ChatRequest(prompt="hi", stream=True))
    assert result[0] == {"provider": "inc", "delta": "thinking"}
    # The payload stays a JSON string, exactly as the legacy route sends it.
    assert result[1] == {"provider": "inc", "tool_call_delta": payload}


def test_mid_stream_failure_yields_an_error_frame_with_no_provider_key(tmp_path: Path) -> None:
    service, audit = service_for(tmp_path, [ExplodingProvider("boom")])
    result = frames(service, ChatRequest(prompt="hi", stream=True))
    assert result[0] == {"provider": "boom", "delta": "partial"}
    assert set(result[1]) == {"error"}
    assert "upstream died mid-stream" in result[1]["error"]
    assert not any("done" in frame for frame in result)
    assert audit.events[0]["result"]["status"] == "error"


def test_pin_mismatch_ends_the_stream_without_a_done_frame(tmp_path: Path) -> None:
    provider = BufferedProvider("pinned", model="actually-served")
    service, audit = service_for(tmp_path, [provider])
    # The pin names a model the provider does not serve.
    service.pipeline.profiles.profiles = ProfileRegistry(
        {"chat": {"pin": {"provider": "pinned", "model": "promised-model"}}, "embedding": {}})
    result = frames(service, ChatRequest(prompt="hi", stream=True, profile="pin"))
    assert set(result[-1]) == {"error"}
    assert "expected model 'promised-model'" in result[-1]["error"]
    assert not any("done" in frame for frame in result)
    assert audit.events[0]["result"]["status"] == "error"


def test_unconfirmed_pin_is_flagged_rather_than_asserted(tmp_path: Path) -> None:
    provider = IncrementalProvider("inc", ["text"], confirm_model=False)
    service, _ = service_for(tmp_path, [provider])
    result = frames(service, ChatRequest(prompt="hi", stream=True, profile="pin"))
    assert result[-1]["profile_pin_unverified"] is True
    assert result[-1]["done"] is True


def test_stage_nine_runs_after_the_stream_not_before_the_first_byte(tmp_path: Path) -> None:
    service, audit = service_for(tmp_path, [BufferedProvider("solo")])

    async def exercise() -> None:
        generator = await service.stream_chat(ChatRequest(prompt="hi", stream=True))
        # The StreamingResponse exists here; nothing has been metered yet.
        assert audit.events == []
        async for _ in generator:
            pass
        assert len(audit.events) == 1

    asyncio.run(exercise())


def test_client_disconnect_still_meters_the_partial_call(tmp_path: Path) -> None:
    service, audit = service_for(tmp_path, [IncrementalProvider("inc", ["one", "two", "three"])])

    async def exercise() -> None:
        generator = await service.stream_chat(ChatRequest(prompt="hi", stream=True))
        async for _ in generator:
            break  # the client hangs up after the first frame
        await generator.aclose()

    asyncio.run(exercise())
    assert len(audit.events) == 1


def test_budget_rejection_before_the_first_byte_is_an_error_not_a_stream(tmp_path: Path) -> None:
    service, audit = service_for(tmp_path, [BufferedProvider("solo")])
    ceiling = tmp_path / "ceiling"
    ceiling.mkdir()
    path, database = budget_files(ceiling, limit=0.000001)
    service.pipeline.budget.controller = BudgetController(path, database)
    # A real price, so the projection is above the ceiling rather than zero.
    service.pipeline.budget.pricing = PricingTable(
        {"models": {}, "providers": {}, "unpriced_default": {"input": 100.0, "output": 100.0}})

    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.stream_chat(ChatRequest(prompt="hi", stream=True, session="run")))
    assert caught.value.status_code == 402
    # Hard rule #4: a call refused before any provider was contacted is still metered.
    assert len(audit.events) == 1


def test_unknown_provider_on_a_stream_raises_before_streaming(tmp_path: Path) -> None:
    service, _ = service_for(tmp_path, [BufferedProvider("solo")])
    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.stream_chat(ChatRequest(prompt="hi", stream=True, provider="nope")))
    assert caught.value.status_code == 400


def test_cache_hit_on_a_streaming_request_answers_with_json_not_frames(tmp_path: Path) -> None:
    """A hit returns the stored body even when `stream` is set.

    That is what the legacy route does (`glc_v5/glc/routes/chat.py:691` returns
    `out` regardless of `req.stream`). It also guards a real crash: on a hit the
    routing and budget stages early-return, so no provider candidate exists, and
    a streaming path that assumed one would raise IndexError *after* the 200 and
    headers were already committed — a truncated stream, not an error.
    """
    provider = BufferedProvider("solo", text="fresh")
    service, audit = service_for(tmp_path, [provider])
    cache = SemanticCache(
        lambda _text, _task: asyncio.sleep(0, result=[1.0, 0.0]),
        tmp_path / "semantic-cache.sqlite",
        config=SemanticCacheConfig(skip_when_stream=False, default_on=True),
    )
    service.attach_semantic_cache(cache)

    async def exercise() -> Any:
        first = await service.chat(ChatRequest(prompt="hello", semantic_cache=True, temperature=0.0))
        assert first["text"] == "fresh"
        return await service.stream_chat(
            ChatRequest(prompt="hello", stream=True, semantic_cache=True, temperature=0.0))

    outcome = asyncio.run(exercise())
    assert isinstance(outcome, dict)
    assert outcome["text"] == "fresh"
    assert outcome["cache"]["hit"] is True
    assert provider.calls == 1  # the cached turn contacted no provider
    assert len(audit.events) == 2  # stage 9 ran for both, hit included
