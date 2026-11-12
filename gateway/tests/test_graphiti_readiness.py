"""Gateway correctness checks required before Graphiti integration."""

import asyncio
from pathlib import Path

from fastapi import HTTPException
import pytest

from gateway.models import ChatRequest, EmbedRequest, ResponseFormat
from gateway.providers import ProviderError, ProviderResult, ProviderUsage
from gateway.config import load_mapping

from test_llm import embedder, service_for


def test_deployment_defaults_to_no_gateway_retries() -> None:
    config = Path(__file__).resolve().parents[1] / "config" / "providers.yaml"
    assert load_mapping(config)["max_retries"] == 0


def test_embedding_dimension_failure_keeps_its_attempt_record(tmp_path: Path) -> None:
    provider = embedder("solo")
    service, ledger = service_for(tmp_path, [provider])

    async def wrong_vector(*args, **kwargs):
        return [1.0]

    provider.embed = wrong_vector
    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.embed(EmbedRequest(text="hello", profile="embed")))
    assert caught.value.status_code == 502
    [row] = ledger.recent()
    assert row["status"] == "error"
    assert len(row["attempted"]) == 1
    assert "expected dimension 2" in row["attempted"][0]["reason"]


def test_budget_refusal_is_recorded_without_calling_provider(tmp_path: Path) -> None:
    provider = embedder("solo")
    service, ledger = service_for(tmp_path, [provider], price=1)
    service.budget.set_limit("session:refused", 0, "lifetime")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.chat(ChatRequest(prompt="hello", session="refused")))
    assert caught.value.status_code == 402
    assert provider.calls == 0
    [row] = ledger.recent()
    assert row["status"] == "refused"
    assert row["usd"] == 0
    assert row["attempted"] == []


@pytest.mark.parametrize("kind", ["chat", "embed"])
@pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
def test_provider_error_status_and_attempt_count(
    tmp_path: Path, kind: str, status: int,
) -> None:
    provider = embedder("solo")
    service, ledger = service_for(tmp_path, [provider])
    assert service.max_retries == 0
    calls = 0

    async def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise ProviderError("provider failed", status=status, retryable=status >= 429)

    setattr(provider, kind, fail)
    request = (ChatRequest(prompt="hello", provider="solo") if kind == "chat"
               else EmbedRequest(text="hello", provider="solo"))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(getattr(service, kind)(request))
    assert caught.value.status_code == status
    assert calls == 1
    [row] = ledger.recent()
    assert row["status"] == "error"
    assert len(row["attempted"]) == 1


@pytest.mark.parametrize("text", ["not JSON", '{"answer": "wrong type"}'])
def test_invalid_structured_output_fails_once_and_keeps_usage(tmp_path: Path, text: str) -> None:
    provider = embedder("solo")
    service, ledger = service_for(tmp_path, [provider])
    calls = []

    async def reply(**kwargs):
        calls.append(kwargs)
        return ProviderResult(provider="solo", model=provider.model, text=text, usage=ProviderUsage(10, 2))

    provider.chat = reply
    request = ChatRequest(prompt="answer", provider="solo", temperature=0.4, max_tokens=123,
                          response_format=ResponseFormat(type="json_schema", schema={
                              "type": "object", "properties": {"answer": {"type": "integer"}},
                              "required": ["answer"],
                          }))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.chat(request))
    assert caught.value.status_code == 502
    assert len(calls) == 1
    assert calls[0]["temperature"] == 0.4 and calls[0]["max_tokens"] == 123
    [row] = ledger.recent()
    assert (row["status"], row["input_tokens"], row["output_tokens"], row["retries"]) == ("error", 10, 2, 0)


@pytest.mark.parametrize("schema", [None, {}, {"type": "object"}])
def test_valid_json_is_parsed_without_changing_generation_parameters(tmp_path: Path, schema) -> None:
    provider = embedder("solo")
    service, _ = service_for(tmp_path, [provider])
    calls = []

    async def reply(**kwargs):
        calls.append(kwargs)
        return ProviderResult(provider="solo", model=provider.model, text='{"answer": 42}')

    provider.chat = reply
    response_format = ResponseFormat(type="json_object" if schema is None else "json_schema", schema=schema)
    result = asyncio.run(service.chat(ChatRequest(prompt="answer", temperature=0.4, max_tokens=123,
                                                 response_format=response_format)))
    assert result["parsed"] == {"answer": 42}
    assert result["retries"] == 0
    assert len(calls) == 1
    assert calls[0]["temperature"] == 0.4 and calls[0]["max_tokens"] == 123


@pytest.mark.parametrize("cap", [1, 2])
def test_chat_and_embed_share_one_concurrency_cap(tmp_path: Path, cap: int) -> None:
    provider = embedder("solo")
    service, ledger = service_for(tmp_path, [provider])
    service.set_max_concurrency(cap)

    async def exercise():
        active = peak = entered = 0
        saturated, release = asyncio.Event(), asyncio.Event()

        async def hold():
            nonlocal active, peak, entered
            active += 1
            entered += 1
            peak = max(peak, active)
            if active >= cap:
                saturated.set()
            try:
                await release.wait()
            finally:
                active -= 1

        async def chat(**kwargs):
            await hold()
            return ProviderResult(provider="solo", model=provider.model, text="ok")

        async def embed(*args, **kwargs):
            await hold()
            return [1.0, 0.0]

        provider.chat, provider.embed = chat, embed
        tasks = [asyncio.create_task(call(request)) for _ in range(3) for call, request in (
            (service.chat, ChatRequest(prompt="hello")),
            (service.embed, EmbedRequest(text="hello", profile="embed")),
        )]
        try:
            await asyncio.wait_for(saturated.wait(), timeout=2)
            # Yield to every scheduled request while provider calls remain blocked.
            await asyncio.sleep(0)
            assert entered == cap
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
        assert peak == cap

    asyncio.run(exercise())
    assert len(ledger.recent()) == 6


@pytest.mark.parametrize("kind", ["chat", "embed"])
@pytest.mark.parametrize("status,expected_calls", [(400, 1), (401, 1), (429, 2), (503, 2)])
def test_explicit_retry_setting_only_retries_transient_errors(tmp_path: Path, kind, status, expected_calls) -> None:
    provider = embedder("solo")
    service, _ = service_for(tmp_path, [provider])
    service.max_retries = 1
    calls = 0

    async def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise ProviderError("provider failed", status=status, retryable=status in {429, 503})

    setattr(provider, kind, fail)
    request = ChatRequest(prompt="hello", provider="solo") if kind == "chat" else EmbedRequest(text="hello", provider="solo")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(getattr(service, kind)(request))
    assert caught.value.status_code == status
    assert calls == expected_calls


@pytest.mark.parametrize("kind", ["chat", "embed"])
def test_permanent_errors_do_not_fall_through_to_another_provider(tmp_path: Path, kind) -> None:
    first, second = embedder("first"), embedder("second")
    service, _ = service_for(tmp_path, [first, second])
    called = []

    async def fail(*args, **kwargs):
        called.append("first")
        raise ProviderError("bad input", status=400)

    async def unexpected(*args, **kwargs):
        called.append("second")
        raise AssertionError("permanent errors must not fail over")

    setattr(first, kind, fail)
    setattr(second, kind, unexpected)
    request = ChatRequest(prompt="hello") if kind == "chat" else EmbedRequest(text="hello")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(getattr(service, kind)(request))
    assert caught.value.status_code == 400
    assert called == ["first"]


@pytest.mark.parametrize("kind", ["chat", "embed"])
def test_cancellation_releases_shared_capacity_and_records_error(tmp_path: Path, kind) -> None:
    provider = embedder("solo")
    service, ledger = service_for(tmp_path, [provider])
    service.set_max_concurrency(1)

    async def exercise():
        entered = asyncio.Event()

        async def block(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        setattr(provider, kind, block)
        request = ChatRequest(prompt="hello") if kind == "chat" else EmbedRequest(text="hello")
        task = asyncio.create_task(getattr(service, kind)(request))
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # A chat request can still use the slot after either kind of call is cancelled.
        async def reply(**kwargs):
            return ProviderResult(provider="solo", model=provider.model, text="ok")

        provider.chat = reply
        result = await asyncio.wait_for(service.chat(ChatRequest(prompt="hello")), timeout=2)
        assert result["text"] == "ok"

    asyncio.run(exercise())
    rows = ledger.recent()
    assert len(rows) == 2
    assert rows[0]["status"] == "ok" and rows[1]["status"] == "error"
