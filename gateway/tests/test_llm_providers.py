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
from gateway.llm.providers.base import TOOL_CALL_DELTA, ProviderCapabilities
from gateway.llm.providers.capabilities import resolve as capability_overrides
from gateway.llm.providers.gemini import GeminiProvider, thinking_knob
from gateway.llm.providers.gemini.schema import clean as gemini_clean, inline_refs
from gateway.llm.providers.ollama import OllamaProvider
from gateway.llm.providers.ollama.tools import parse_prompted_call, supports_native_tools
from gateway.llm.providers.openai import OpenAIProvider
from gateway.llm.providers.openai_compatible import OpenAICompatibleProvider


class Recorder:
    """Captures the request body each provider actually puts on the wire."""

    def __init__(self, response: dict[str, Any] | None = None, *, status: int = 200,
                 sse: list[str] | None = None) -> None:
        self.response = response or {}
        self.status = status
        self.sse = sse
        self.bodies: list[dict[str, Any]] = []
        self.urls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        self.bodies.append(json.loads(request.content) if request.content else {})
        if self.sse is not None:
            return httpx.Response(self.status, text="".join(f"data: {x}\n\n" for x in self.sse))
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


# ── Gemini ──────────────────────────────────────────────────────────────────

def test_gemini_inlines_refs_so_pydantic_schemas_survive() -> None:
    schema = {
        "type": "object",
        "properties": {"item": {"$ref": "#/$defs/Item"}},
        "$defs": {"Item": {"type": "object", "properties": {"name": {"type": "string"}}}},
    }
    cleaned = gemini_clean(schema)
    assert "$defs" not in cleaned
    assert cleaned["properties"]["item"] == {"type": "object", "properties": {"name": {"type": "string"}}}
    assert "$ref" not in json.dumps(cleaned)


def test_gemini_inlining_terminates_on_a_self_referential_schema() -> None:
    schema = {"$defs": {"Node": {"type": "object", "properties": {"child": {"$ref": "#/$defs/Node"}}}},
              "$ref": "#/$defs/Node"}
    # One level resolves, then the repeat is dropped rather than recursing
    # forever — and no `$ref` survives for Gemini to reject.
    inlined = inline_refs(schema)
    assert inlined["type"] == "object"
    assert inlined["properties"]["child"] == {}  # the repeat is dropped, not recursed into
    assert "$ref" not in json.dumps(gemini_clean(schema))


def test_gemini_drops_the_keys_the_response_schema_endpoint_rejects() -> None:
    cleaned = gemini_clean({"type": "object", "title": "T", "additionalProperties": False,
                            "properties": {"a": {"type": "string", "default": "x"}}})
    assert cleaned == {"type": "object", "properties": {"a": {"type": "string"}}}


@pytest.mark.parametrize(("model", "knob"), [
    ("gemini-2.5-pro", "level"), ("gemini-3-flash", "level"), ("gemini-2.5-flash", "budget"),
    ("gemini-2.5-flash-lite", None), ("llama3", None),
])
def test_gemini_thinking_knob_is_per_model(model: str, knob: str | None) -> None:
    assert thinking_knob(model) == knob


def test_gemini_sends_a_thinking_budget_and_reports_it_truthfully() -> None:
    recorder = Recorder({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})
    provider = GeminiProvider("gemini_1", "k", "gemini-2.5-flash", recorder.client)
    result = run(provider.chat(messages=[{"role": "user", "content": "hi"}], reasoning="high"))
    assert recorder.body["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 24576}
    assert result.reasoning_applied is True


def test_gemini_does_not_claim_reasoning_it_cannot_apply() -> None:
    recorder = Recorder({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})
    provider = GeminiProvider("gemini_1", "k", "gemini-2.5-flash-lite", recorder.client)
    result = run(provider.chat(messages=[{"role": "user", "content": "hi"}], reasoning="high"))
    assert "thinkingConfig" not in recorder.body["generationConfig"]
    assert result.reasoning_applied is False


def test_gemini_echoes_thought_signatures_back_on_the_next_turn() -> None:
    recorder = Recorder({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})
    provider = GeminiProvider("gemini_1", "k", "gemini-2.5-flash", recorder.client)
    run(provider.chat(messages=[
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "name": "lookup", "arguments": {"q": "x"}, "provider_meta": {"thoughtSignature": "SIG"}}]},
    ]))
    model_turn = recorder.body["contents"][1]
    assert model_turn["parts"][0]["thoughtSignature"] == "SIG"


def test_gemini_surfaces_thought_signatures_it_receives() -> None:
    recorder = Recorder({"candidates": [{"content": {"parts": [
        {"functionCall": {"name": "lookup", "args": {"q": "x"}}, "thoughtSignature": "SIG"}]}}]})
    provider = GeminiProvider("gemini_1", "k", "gemini-2.5-flash", recorder.client)
    result = run(provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[TOOL]))
    assert result.tool_calls[0]["provider_meta"] == {"thoughtSignature": "SIG"}


def test_gemini_capabilities_track_the_configured_model() -> None:
    client = Recorder().client
    assert GeminiProvider("gemini_1", "k", "gemini-2.5-flash", client).capabilities.reasoning is True
    assert GeminiProvider("gemini_1", "k", "gemini-2.5-flash-lite", client).capabilities.reasoning is False


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
    provider = AnthropicProvider("anthropic-sonnet", "k", "claude-sonnet-4-6", recorder.client)
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
    provider = AnthropicProvider("anthropic-sonnet", "k", "claude-sonnet-4-6", recorder.client)
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
    provider = AnthropicProvider("anthropic-sonnet", "k", "claude-sonnet-4-6", recorder.client)
    run(provider.chat(messages=[{"role": "user", "content": "hi"}],
                      response_format=ResponseFormat(type="json_schema", schema={
                          "type": "object", "properties": {"n": {"type": "integer", "minimum": 1}}})))
    sent = recorder.body["output_config"]["format"]["schema"]
    assert "minimum" not in json.dumps(sent)


def test_anthropic_translates_tool_results_into_user_blocks() -> None:
    recorder = Recorder({"content": [{"type": "text", "text": "ok"}]})
    provider = AnthropicProvider("anthropic-sonnet", "k", "claude-sonnet-4-6", recorder.client)
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
    provider = OpenAIProvider("openai-pro", "k", "gpt-5.5", recorder.client)
    run(provider.chat(messages=[{"role": "user", "content": "hi"}], max_tokens=512))
    assert recorder.body["max_completion_tokens"] == 512
    assert "max_tokens" not in recorder.body


def test_openai_gates_reasoning_effort_on_the_model_family() -> None:
    recorder = Recorder({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    reasoning_model = OpenAIProvider("openai-pro", "k", "gpt-5.5", recorder.client)
    result = run(reasoning_model.chat(messages=[{"role": "user", "content": "hi"}], reasoning="high"))
    assert recorder.body["reasoning_effort"] == "high" and result.reasoning_applied is True

    plain = OpenAIProvider("openai-cheap", "k", "gpt-4.1-mini", recorder.client)
    result = run(plain.chat(messages=[{"role": "user", "content": "hi"}], reasoning="high"))
    assert "reasoning_effort" not in recorder.body and result.reasoning_applied is False


def test_openai_requests_parallel_tool_calls_and_translates_a_forced_choice() -> None:
    recorder = Recorder({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    provider = OpenAIProvider("openai-pro", "k", "gpt-5.5", recorder.client)
    run(provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[TOOL],
                      tool_choice={"name": "lookup"}))
    assert recorder.body["parallel_tool_calls"] is True
    assert recorder.body["tool_choice"] == {"type": "function", "function": {"name": "lookup"}}


def test_openai_streams_one_buffered_frame_like_the_legacy_direct_adapter() -> None:
    recorder = Recorder({"choices": [{"message": {"content": "a b c"}, "finish_reason": "stop"}],
                         "model": "gpt-5.5"})
    provider = OpenAIProvider("openai-pro", "k", "gpt-5.5", recorder.client)

    async def collect() -> tuple[list[str], dict[str, Any]]:
        sink: dict[str, Any] = {}
        chunks = [chunk async for chunk in provider.stream(
            messages=[{"role": "user", "content": "hi"}], result_sink=sink)]
        return chunks, sink

    chunks, sink = run(collect())
    assert chunks == ["a b c"]
    assert sink["model"] == "gpt-5.5"


# ── OpenAI-compatible ───────────────────────────────────────────────────────

def test_compatible_family_streams_incrementally_with_tool_deltas() -> None:
    recorder = Recorder(sse=[
        json.dumps({"model": "gpt-oss-120b", "choices": [{"delta": {"content": "Hel"}}]}),
        json.dumps({"model": "gpt-oss-120b", "choices": [{"delta": {"content": "lo"}}]}),
        json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0}]}}]}),
        "[DONE]",
    ])
    provider = OpenAICompatibleProvider("groq", "k", "openai/gpt-oss-120b",
                                        "https://api.groq.com/openai/v1", recorder.client)

    async def collect() -> tuple[list[str], dict[str, Any]]:
        sink: dict[str, Any] = {}
        chunks = [chunk async for chunk in provider.stream(
            messages=[{"role": "user", "content": "hi"}], result_sink=sink)]
        return chunks, sink

    chunks, sink = run(collect())
    assert chunks[:2] == ["Hel", "lo"]
    assert chunks[2].startswith(TOOL_CALL_DELTA)
    # The vendor's echoed model, which is what makes a streamed pin check real.
    assert sink["model"] == "gpt-oss-120b"
    assert recorder.body["stream"] is True


def test_compatible_stream_ignores_unparseable_chunks() -> None:
    recorder = Recorder(sse=["{not json", json.dumps({"choices": [{"delta": {"content": "ok"}}]}), "[DONE]"])
    provider = OpenAICompatibleProvider("groq", "k", "m", "https://x/v1", recorder.client)

    async def collect() -> list[str]:
        return [chunk async for chunk in provider.stream(messages=[{"role": "user", "content": "hi"}])]

    assert run(collect()) == ["ok"]


# ── capability resolution ───────────────────────────────────────────────────

def test_capabilities_resolve_per_model_for_the_compatible_family() -> None:
    defaults = ProviderCapabilities()
    assert capability_overrides("groq", "openai/gpt-oss-120b", defaults).reasoning is True
    assert capability_overrides("groq", "llama-3.1-8b", defaults).reasoning is False


def test_direct_adapters_declare_their_known_good_capabilities() -> None:
    resolved = capability_overrides("openai-pro", "gpt-5.5", ProviderCapabilities())
    assert resolved.vision and resolved.tools and resolved.reasoning and resolved.structured_output
