"""Per-provider dialect tests — the checklist Plan 04 §5 asks for.

Each test pins one capability that exists in the read-only legacy source
(`glc_v5/glc/providers.py`, `glc_v5/glc/direct_providers.py`) to its migrated
counterpart, so "every code path has a counterpart" is a claim a test makes
rather than a claim a reviewer has to take on trust.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from gateway.llm.models import CacheableSystemBlock, ResponseFormat, ToolDef
from gateway.llm.providers.anthropic import AnthropicProvider
from gateway.llm.providers.anthropic.schema import clean as anthropic_clean
from gateway.llm.providers.base import ProviderCapabilities
from gateway.llm.providers.capabilities import resolve as capability_overrides
from gateway.llm.providers.ollama import OllamaProvider
from gateway.llm.providers.ollama.tools import parse_prompted_call, supports_native_tools
from gateway.llm.providers.openai import OpenAIProvider


class Recorder:
    """Captures the request body each provider actually puts on the wire."""

    def __init__(self, response: dict[str, Any] | None = None, *, status: int = 200) -> None:
        self.response = response or {}
        self.status = status
        self.bodies: list[dict[str, Any]] = []
        self.urls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        self.bodies.append(json.loads(request.content) if request.content else {})
        return httpx.Response(self.status, json=self.response)

    @property
    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    @property
    def body(self) -> dict[str, Any]:
        return self.bodies[-1]


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


TOOL = ToolDef(name="lookup", description="find a thing",
               input_schema={"type": "object", "properties": {"q": {"type": "string"}}})


# ── Ollama ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("model", "native"), [("qwen3:8b", True), ("llama3.1:8b", True), ("phi4", False)])
def test_ollama_native_tool_support_is_per_model(model: str, native: bool) -> None:
    assert supports_native_tools(model) is native


def test_ollama_falls_back_to_prompted_tools_when_the_model_has_no_native_api() -> None:
    recorder = Recorder({"message": {"content": '{"tool_call":{"name":"lookup","arguments":{"q":"x"}}}'}})
    provider = OllamaProvider("local", "phi4", recorder.client)
    result = run(provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[TOOL]))
    assert "tools" not in recorder.body  # no native array for a model that cannot take one
    assert "lookup" in recorder.body["messages"][0]["content"]
    assert result.tool_call_dialect == "prompted_fallback"
    assert result.tool_calls == [{"id": result.tool_calls[0]["id"], "name": "lookup", "arguments": {"q": "x"}}]
    assert result.text == ""  # the JSON line is a call, not prose for the caller


def test_ollama_uses_the_native_tool_array_when_the_model_supports_it() -> None:
    recorder = Recorder({"message": {"content": "", "tool_calls": [
        {"function": {"name": "lookup", "arguments": {"q": "x"}}}]}})
    provider = OllamaProvider("local", "qwen3:8b", recorder.client)
    result = run(provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[TOOL]))
    assert recorder.body["tools"][0]["function"]["name"] == "lookup"
    assert result.tool_call_dialect == "native"


def test_ollama_parses_a_prompted_call_out_of_surrounding_prose() -> None:
    parsed = parse_prompted_call('Sure! {"tool_call":{"name":"lookup","arguments":{"q":"x"}}} done')
    assert parsed is not None and parsed["name"] == "lookup"
    assert parse_prompted_call("no call here") is None


def test_ollama_moves_images_into_its_own_field() -> None:
    recorder = Recorder({"message": {"content": "ok"}})
    provider = OllamaProvider("local", "llava", recorder.client, vision=True)
    run(provider.chat(messages=[{"role": "user", "content": [
        {"type": "text", "text": "what is this"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}]))
    message = recorder.body["messages"][0]
    assert message["content"] == "what is this"
    assert message["images"] == ["AAAA"]


# ── Anthropic ───────────────────────────────────────────────────────────────

def test_anthropic_marks_cacheable_system_blocks() -> None:
    recorder = Recorder({"content": [{"type": "text", "text": "ok"}], "usage": {"cache_creation_input_tokens": 42}})
    provider = AnthropicProvider("anthropic", "k", "claude-sonnet-4-6", recorder.client)
    system = [CacheableSystemBlock(text="long stable preamble", cache=True),
              CacheableSystemBlock(text="volatile tail", cache=False)]
    result = run(provider.chat(messages=[{"role": "user", "content": "hi"}], system=system))
    assert recorder.body["system"] == [
        {"type": "text", "text": "long stable preamble", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "volatile tail"},
    ]
    assert result.usage.cache_creation_input_tokens == 42


def test_anthropic_cache_system_flag_marks_every_block() -> None:
    recorder = Recorder({"content": [{"type": "text", "text": "ok"}]})
    provider = AnthropicProvider("anthropic", "k", "claude-sonnet-4-6", recorder.client)
    run(provider.chat(messages=[{"role": "user", "content": "hi"}], system="preamble", cache_system=True))
    assert recorder.body["system"] == [{"type": "text", "text": "preamble"}]


def test_anthropic_schema_restates_constraints_it_must_drop() -> None:
    cleaned = anthropic_clean({"type": "object", "properties": {
        "age": {"type": "integer", "minimum": 0, "maximum": 120}}})
    description = cleaned["properties"]["age"]["description"]
    assert "greater than or equal to 0" in description and "less than or equal to 120" in description
    assert "minimum" not in cleaned["properties"]["age"]
    assert cleaned["additionalProperties"] is False


def test_anthropic_sends_the_cleaned_schema_for_structured_output() -> None:
    recorder = Recorder({"content": [{"type": "text", "text": "{}"}]})
    provider = AnthropicProvider("anthropic", "k", "claude-sonnet-4-6", recorder.client)
    run(provider.chat(messages=[{"role": "user", "content": "hi"}],
                      response_format=ResponseFormat(type="json_schema", schema={
                          "type": "object", "properties": {"n": {"type": "integer", "minimum": 1}}})))
    sent = recorder.body["output_config"]["format"]["schema"]
    assert "minimum" not in json.dumps(sent)


def test_anthropic_translates_tool_results_into_user_blocks() -> None:
    recorder = Recorder({"content": [{"type": "text", "text": "ok"}]})
    provider = AnthropicProvider("anthropic", "k", "claude-sonnet-4-6", recorder.client)
    run(provider.chat(messages=[
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "lookup", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "42"},
    ]))
    turns = recorder.body["messages"]
    assert turns[1]["content"][0]["type"] == "tool_use"
    assert turns[2]["role"] == "user" and turns[2]["content"][0]["type"] == "tool_result"


# ── OpenAI ──────────────────────────────────────────────────────────────────

def test_openai_sends_max_completion_tokens_not_max_tokens() -> None:
    recorder = Recorder({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    provider = OpenAIProvider("openai", "k", "gpt-5.5", recorder.client)
    run(provider.chat(messages=[{"role": "user", "content": "hi"}], max_tokens=512))
    assert recorder.body["max_completion_tokens"] == 512
    assert "max_tokens" not in recorder.body


def test_openai_gates_reasoning_effort_on_the_model_family() -> None:
    recorder = Recorder({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    reasoning_model = OpenAIProvider("openai", "k", "gpt-5.5", recorder.client)
    result = run(reasoning_model.chat(messages=[{"role": "user", "content": "hi"}], reasoning="high"))
    assert recorder.body["reasoning_effort"] == "high" and result.reasoning_applied is True

    plain = OpenAIProvider("openai", "k", "gpt-4.1-mini", recorder.client)
    result = run(plain.chat(messages=[{"role": "user", "content": "hi"}], reasoning="high"))
    assert "reasoning_effort" not in recorder.body and result.reasoning_applied is False


def test_openai_requests_parallel_tool_calls_and_translates_a_forced_choice() -> None:
    recorder = Recorder({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    provider = OpenAIProvider("openai", "k", "gpt-5.5", recorder.client)
    run(provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[TOOL],
                      tool_choice={"name": "lookup"}))
    assert recorder.body["parallel_tool_calls"] is True
    assert recorder.body["tool_choice"] == {"type": "function", "function": {"name": "lookup"}}


# ── OpenAI-compatible ───────────────────────────────────────────────────────


# ── capability resolution ───────────────────────────────────────────────────

def test_direct_adapters_declare_their_known_good_capabilities() -> None:
    resolved = capability_overrides("openai", "gpt-5.5", ProviderCapabilities())
    assert resolved.vision and resolved.tools and resolved.reasoning and resolved.structured_output


# Provider construction and checked-in pricing must agree with the profiles.
@pytest.fixture
def configured_registry(monkeypatch: pytest.MonkeyPatch):
    import os
    from pathlib import Path
    from gateway.llm.providers.registry import build_provider_registry

    for name in tuple(os.environ):
        if name.endswith(('_MODEL', '_API_KEY')) or '_API_KEY_' in name:
            monkeypatch.delenv(name)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    return build_provider_registry(Recorder().client, config_dir=Path(__file__).resolve().parents[1] / 'config')


def test_registry_contains_only_supported_providers(configured_registry) -> None:
    import yaml
    from pathlib import Path

    local = yaml.safe_load((Path(__file__).resolve().parents[1] / 'config/local_models.yaml').read_text())['models']
    assert set(configured_registry.providers) == {'anthropic', 'openai', *local}
    assert configured_registry.order[:2] == ['openai', 'anthropic']


def test_removed_credentials_do_not_register_providers(monkeypatch, configured_registry) -> None:
    from pathlib import Path
    from gateway.llm.providers.registry import build_provider_registry

    for name in ('GEMINI_API_KEY', 'GEMINI_API_KEY_1', 'GROQ_API_KEY', 'CEREBRAS_API_KEY',
                 'NVIDIA_API_KEY', 'OPEN_ROUTER_API_KEY', 'GITHUB_ACCESS_TOKEN'):
        monkeypatch.setenv(name, 'unused-test-key')
    registry = build_provider_registry(Recorder().client, config_dir=Path(__file__).resolve().parents[1] / 'config')
    assert set(registry.providers) == set(configured_registry.providers)


def test_anthropic_request_can_override_the_default_model() -> None:
    recorder = Recorder({'content': [{'type': 'text', 'text': 'ok'}]})
    provider = AnthropicProvider('anthropic', 'k', 'claude-sonnet-4-6', recorder.client)
    result = run(provider.chat(messages=[{'role': 'user', 'content': 'hi'}], model='claude-haiku-4-5'))
    assert recorder.body['model'] == result.model == 'claude-haiku-4-5'


def test_profiles_and_default_models_have_exact_prices(configured_registry) -> None:
    import yaml
    from pathlib import Path
    from gateway.llm.economics.pricing import PricingTable

    config = Path(__file__).resolve().parents[1] / 'config'
    pricing = PricingTable.from_yaml(config / 'pricing.yaml')
    profiles = yaml.safe_load((config / 'profiles.yaml').read_text())
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
    from pathlib import Path
    from gateway.llm.economics.pricing import PricingTable
    from gateway.llm.providers.base import ProviderUsage

    pricing = PricingTable.from_yaml(Path(__file__).resolve().parents[1] / 'config/pricing.yaml')
    price = pricing.price_for(provider, model)
    assert price.source == f'models.{model}'
    assert (price.input_usd_per_mtok, price.output_usd_per_mtok) == (input_rate, output_rate)
    cost = pricing.cost(provider, model, ProviderUsage(1_000_000, 1_000_000))
    assert cost['total_usd'] == input_rate + output_rate
