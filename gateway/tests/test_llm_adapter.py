"""The any-llm adapter puts the right request on the wire and reads the reply back correctly.

Each provider SDK is handed an httpx mock transport, so these tests see the exact body
each vendor receives without a network call.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from gateway.llm.models import CacheableSystemBlock, ResponseFormat, ToolDef
from gateway.llm.providers.base import ProviderCapabilities, ProviderError, ProviderUsage
from gateway.llm.providers.llm import LLMProvider
from gateway.llm.providers.prompted_tools import parse_prompted_call, supports_native_tools

CONFIG = Path(__file__).resolve().parents[1] / "config"
TOOL = ToolDef(name="lookup", description="find a thing",
               input_schema={"type": "object", "properties": {"q": {"type": "string"}}})
HI = [{"role": "user", "content": "hi"}]


class Recorder:
    """Captures the request body each provider actually puts on the wire."""

    def __init__(self, *responses: dict[str, Any], status: int = 200) -> None:
        self.responses, self.status = list(responses), status
        self.bodies: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content) if request.content else {})
        status = self.status if len(self.bodies) == 1 else 200
        return httpx.Response(status, json=self.responses[min(len(self.bodies), len(self.responses)) - 1])

    @property
    def body(self) -> dict[str, Any]:
        return self.bodies[-1]

    def provider(self, kind: str, model: str, **kwargs: Any) -> LLMProvider:
        transport = httpx.MockTransport(self.handler)
        if kind == "ollama":
            return LLMProvider("local", kind, model, ProviderCapabilities(), api_base="http://localhost:11434",
                               client_args={"transport": transport}, **kwargs)
        return LLMProvider(kind, kind, model, ProviderCapabilities(), api_key="k",
                           client_args={"http_client": httpx.AsyncClient(transport=transport)}, **kwargs)


def claude(content: list[dict[str, Any]] | None = None, **usage: int) -> dict[str, Any]:
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6",
            "content": content or [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 2, **usage}}


def gpt(message: dict[str, Any] | None = None, **usage: Any) -> dict[str, Any]:
    return {"id": "c1", "object": "chat.completion", "created": 1, "model": "gpt-5.5",
            "choices": [{"index": 0, "finish_reason": "stop", "message": message or {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12, **usage}}


def local(message: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"model": "phi4", "created_at": "2026-10-19T00:00:00.000000Z", "done": True, "done_reason": "stop",
            "message": message or {"role": "assistant", "content": "ok"}, "prompt_eval_count": 30, "eval_count": 7}


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


# ── Ollama ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("model", "native"), [("qwen3:8b", True), ("llama3.1:8b", True), ("phi4", False)])
def test_ollama_native_tool_support_is_per_model(model: str, native: bool) -> None:
    assert supports_native_tools(model) is native


def test_ollama_falls_back_to_prompted_tools_when_the_model_has_no_native_api() -> None:
    recorder = Recorder(local({"role": "assistant", "content": '{"tool_call":{"name":"lookup","arguments":{"q":"x"}}}'}))
    result = run(recorder.provider("ollama", "phi4").chat(messages=HI, tools=[TOOL]))
    assert not recorder.body.get("tools")  # no native array for a model that cannot take one
    assert "lookup" in recorder.body["messages"][0]["content"]
    assert result.tool_call_dialect == "prompted_fallback"
    assert result.tool_calls == [{"id": result.tool_calls[0]["id"], "name": "lookup", "arguments": {"q": "x"}}]
    assert result.text == ""  # the JSON line is a call, not prose for the caller


def test_ollama_uses_the_native_tool_array_when_the_model_supports_it() -> None:
    recorder = Recorder(local({"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "lookup", "arguments": {"q": "x"}}}]}))
    result = run(recorder.provider("ollama", "qwen3:8b").chat(messages=HI, tools=[TOOL]))
    assert recorder.body["tools"][0]["function"]["name"] == "lookup"
    assert result.tool_call_dialect == "native"
    assert result.tool_calls[0]["arguments"] == {"q": "x"}


def test_ollama_parses_a_prompted_call_out_of_surrounding_prose() -> None:
    parsed = parse_prompted_call('Sure! {"tool_call":{"name":"lookup","arguments":{"q":"x"}}} done')
    assert parsed is not None and parsed["name"] == "lookup"
    assert parse_prompted_call("no call here") is None


def test_ollama_moves_images_into_its_own_field_and_turns_thinking_off() -> None:
    recorder = Recorder(local())
    run(recorder.provider("ollama", "gemma4:12b", needs_think_false=True).chat(messages=[{"role": "user", "content": [
        {"type": "text", "text": "what is this"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}]))
    message = recorder.body["messages"][0]
    assert message["content"] == "what is this"
    assert message["images"] == ["AAAA"]
    assert recorder.body["think"] is False


def test_ollama_reports_the_requested_model_and_its_token_counts() -> None:
    recorder = Recorder({**local(), "model": "gemma4:12b-latest"})
    result = run(recorder.provider("ollama", "gemma4:12b").chat(messages=HI, max_tokens=64))
    assert result.model == "gemma4:12b"  # profiles pin the requested name
    assert recorder.body["options"]["num_predict"] == 64
    assert (result.usage.input_tokens, result.usage.output_tokens) == (30, 7)


def test_ollama_embeds() -> None:
    recorder = Recorder({"model": "nomic-embed-text", "embeddings": [[0.1] * 768]})
    vector = run(recorder.provider("ollama", "nomic-embed-text").embed("hello"))
    assert len(vector) == 768
    assert (recorder.body["model"], recorder.body["input"]) == ("nomic-embed-text", "hello")


# ── Anthropic ───────────────────────────────────────────────────────────────

def test_anthropic_marks_cacheable_system_blocks() -> None:
    recorder = Recorder(claude(cache_creation_input_tokens=42))
    system = [CacheableSystemBlock(text="long stable preamble", cache=True),
              CacheableSystemBlock(text="volatile tail", cache=False)]
    result = run(recorder.provider("anthropic", "claude-sonnet-4-6").chat(messages=HI, system=system))
    assert recorder.body["system"] == [
        {"type": "text", "text": "long stable preamble", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "volatile tail"},
    ]
    assert result.usage.cache_creation_input_tokens == 42


def test_anthropic_cache_system_flag_marks_every_block() -> None:
    recorder = Recorder(claude())
    run(recorder.provider("anthropic", "claude-sonnet-4-6").chat(messages=HI, system="preamble", cache_system=True))
    assert recorder.body["system"] == [{"type": "text", "text": "preamble"}]


def test_anthropic_input_tokens_include_cache_so_pricing_bills_each_class_once() -> None:
    from gateway.llm.economics.pricing import PricingTable

    recorder = Recorder(claude(input_tokens=5, cache_creation_input_tokens=1000, cache_read_input_tokens=3000))
    result = run(recorder.provider("anthropic", "claude-haiku-4-5").chat(messages=HI))
    assert result.usage == ProviderUsage(input_tokens=4005, output_tokens=2,
                                         cache_creation_input_tokens=1000, cache_read_input_tokens=3000)
    # Haiku 4.5: $1/M input, cache write 1.25x, cache read 0.1x, $5/M output.
    cost = PricingTable.from_yaml(CONFIG / "pricing.yaml").cost("anthropic", "claude-haiku-4-5", result.usage)
    assert cost["total_usd"] == pytest.approx((5 + 1000 * 1.25 + 3000 * 0.1 + 2 * 5) / 1_000_000)


def test_anthropic_restates_schema_constraints_it_must_drop() -> None:
    recorder = Recorder(claude([{"type": "text", "text": "{}"}]))
    run(recorder.provider("anthropic", "claude-sonnet-4-6").chat(messages=HI, response_format=ResponseFormat(
        type="json_schema", schema={"type": "object", "properties": {"n": {"type": "integer", "minimum": 1}}})))
    sent = recorder.body["output_config"]["format"]["schema"]
    assert "minimum" not in sent["properties"]["n"]  # not sent as a constraint...
    assert "minimum: 1" in sent["properties"]["n"]["description"]  # ...but still shown to the model
    assert sent["additionalProperties"] is False


def test_anthropic_translates_tool_results_into_user_blocks() -> None:
    recorder = Recorder(claude())
    run(recorder.provider("anthropic", "claude-sonnet-4-6").chat(messages=[
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "lookup", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "42"},
    ]))
    turns = recorder.body["messages"]
    assert turns[1]["content"][0]["type"] == "tool_use"
    assert turns[2]["role"] == "user" and turns[2]["content"][0]["type"] == "tool_result"


def test_anthropic_reads_back_tool_calls() -> None:
    recorder = Recorder({**claude([{"type": "tool_use", "id": "toolu_2", "name": "lookup", "input": {"q": "y"}}]),
                         "stop_reason": "tool_use"})
    result = run(recorder.provider("anthropic", "claude-sonnet-4-6").chat(messages=HI, tools=[TOOL]))
    assert result.tool_calls == [{"id": "toolu_2", "name": "lookup", "arguments": {"q": "y"}}]
    assert result.stop_reason == "tool_use" and result.tool_call_dialect == "native"


def test_anthropic_retries_once_without_thinking_when_the_model_rejects_it() -> None:
    recorder = Recorder({"type": "error", "error": {"type": "invalid_request_error", "message": "thinking not supported"}},
                        claude(), status=400)
    result = run(recorder.provider("anthropic", "claude-haiku-4-5").chat(messages=HI, reasoning="low", max_tokens=2048))
    assert recorder.bodies[0]["thinking"] == {"type": "enabled", "budget_tokens": 1024}
    assert "thinking" not in recorder.bodies[1]
    assert result.reasoning_applied is False and result.text == "ok"


@pytest.mark.parametrize(("status", "retryable"), [(429, True), (529, True), (400, False), (401, False)])
def test_errors_keep_their_status_and_retryability(status: int, retryable: bool) -> None:
    recorder = Recorder({"type": "error", "error": {"type": "x", "message": "nope"}}, status=status)
    with pytest.raises(ProviderError) as caught:
        run(recorder.provider("anthropic", "claude-haiku-4-5").chat(messages=HI))
    assert (caught.value.status, caught.value.retryable) == (status, retryable)
    assert len(recorder.bodies) == 1  # the SDK does not retry on its own; the stage does


# ── OpenAI ──────────────────────────────────────────────────────────────────

def test_openai_sends_max_completion_tokens_not_max_tokens() -> None:
    recorder = Recorder(gpt())
    run(recorder.provider("openai", "gpt-5.5").chat(messages=HI, max_tokens=512))
    assert recorder.body["max_completion_tokens"] == 512
    assert "max_tokens" not in recorder.body


def test_openai_gates_reasoning_effort_on_the_model_family() -> None:
    recorder = Recorder(gpt())
    result = run(recorder.provider("openai", "gpt-5.5").chat(messages=HI, reasoning="high"))
    assert recorder.body["reasoning_effort"] == "high" and result.reasoning_applied is True

    result = run(recorder.provider("openai", "gpt-4.1-mini").chat(messages=HI, reasoning="high"))
    assert "reasoning_effort" not in recorder.body and result.reasoning_applied is False


def test_openai_requests_parallel_tool_calls_and_translates_a_forced_choice() -> None:
    recorder = Recorder(gpt())
    run(recorder.provider("openai", "gpt-5.5").chat(messages=HI, tools=[TOOL], tool_choice={"name": "lookup"}))
    assert recorder.body["parallel_tool_calls"] is True
    assert recorder.body["tool_choice"] == {"type": "function", "function": {"name": "lookup"}}


def test_openai_reports_cached_tokens_inside_input_tokens() -> None:
    recorder = Recorder(gpt(prompt_tokens=4000, prompt_tokens_details={"cached_tokens": 2048}))
    result = run(recorder.provider("openai", "gpt-5.5").chat(messages=HI))
    assert (result.usage.input_tokens, result.usage.cache_read_input_tokens) == (4000, 2048)


# ── registry and prices ─────────────────────────────────────────────────────

@pytest.fixture
def configured_registry(monkeypatch: pytest.MonkeyPatch):
    from gateway.llm.providers.registry import build_provider_registry

    for name in tuple(os.environ):
        if name.endswith(('_MODEL', '_API_KEY')) or '_API_KEY_' in name:
            monkeypatch.delenv(name)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    return build_provider_registry(config_dir=CONFIG)


def test_registry_contains_only_supported_providers(configured_registry) -> None:
    import yaml

    local_models = yaml.safe_load((CONFIG / 'local_models.yaml').read_text())['models']
    assert set(configured_registry.providers) == {'anthropic', 'openai', *local_models}
    assert configured_registry.order[:2] == ['openai', 'anthropic']
    hosted = configured_registry.get('anthropic').capabilities
    assert hosted.vision and hosted.tools and hosted.reasoning and hosted.structured_output
    assert configured_registry.get('phi4-local').capabilities.vision is False


def test_removed_credentials_do_not_register_providers(monkeypatch, configured_registry) -> None:
    from gateway.llm.providers.registry import build_provider_registry

    for name in ('GEMINI_API_KEY', 'GEMINI_API_KEY_1', 'GROQ_API_KEY', 'CEREBRAS_API_KEY',
                 'NVIDIA_API_KEY', 'OPEN_ROUTER_API_KEY', 'GITHUB_ACCESS_TOKEN'):
        monkeypatch.setenv(name, 'unused-test-key')
    registry = build_provider_registry(config_dir=CONFIG)
    assert set(registry.providers) == set(configured_registry.providers)


def test_anthropic_request_can_override_the_default_model() -> None:
    recorder = Recorder(claude())
    run(recorder.provider("anthropic", "claude-sonnet-4-6").chat(messages=HI, model='claude-haiku-4-5'))
    assert recorder.body['model'] == 'claude-haiku-4-5'


def test_profiles_and_default_models_have_exact_prices(configured_registry) -> None:
    import yaml
    from gateway.llm.economics.pricing import PricingTable

    pricing = PricingTable.from_yaml(CONFIG / 'pricing.yaml')
    profiles = yaml.safe_load((CONFIG / 'profiles.yaml').read_text())
    specs = [spec for kind in ('chat', 'embedding') for spec in profiles[kind].values()]
    specs += [{'provider': name, 'model': p.model} for name, p in configured_registry.providers.items()]
    for spec in specs:
        assert spec['provider'] in configured_registry.providers
        assert pricing.price_for(spec['provider'], spec['model']).source == f"models.{spec['model']}"


@pytest.mark.parametrize(('provider', 'model', 'input_rate', 'output_rate'), [
    ('anthropic', 'claude-haiku-4-5', 1, 5),
    ('anthropic', 'claude-sonnet-4-6', 3, 15),
    ('anthropic', 'claude-opus-4-8', 5, 25),
    ('openai', 'gpt-5.4-nano', .20, 1.25),
    ('openai', 'gpt-5.4-mini', .75, 4.50),
    ('openai', 'gpt-5.5', 5, 30),
])
def test_hosted_models_have_verified_prices(provider, model, input_rate, output_rate) -> None:
    from gateway.llm.economics.pricing import PricingTable

    pricing = PricingTable.from_yaml(CONFIG / 'pricing.yaml')
    price = pricing.price_for(provider, model)
    assert price.source == f'models.{model}'
    assert (price.input_usd_per_mtok, price.output_usd_per_mtok) == (input_rate, output_rate)
    cost = pricing.cost(provider, model, ProviderUsage(1_000_000, 1_000_000))
    assert cost['total_usd'] == input_rate + output_rate
