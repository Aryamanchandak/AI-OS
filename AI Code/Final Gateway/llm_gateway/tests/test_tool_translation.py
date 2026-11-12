from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))

import providers


ADD_TOOL = {
    "name": "add",
    "description": "Return a + b.",
    "input_schema": {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    },
}


MESSAGES = [{"role": "user", "content": "What is 7 plus 5? Use the add tool."}]


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.requests.append({"url": url, **kwargs})
        return self.responses.pop(0)


def install_fake_http(monkeypatch, payload: dict) -> FakeAsyncClient:
    fake = FakeAsyncClient([FakeResponse(payload)])
    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda *args, **kwargs: fake)
    return fake


@pytest.mark.asyncio
async def test_openai_translates_tools_and_normalizes_tool_calls(monkeypatch):
    fake = install_fake_http(monkeypatch, {
        "choices": [{
            "message": {
                "content": None,
                "tool_calls": [{
                    "id": "call_openai",
                    "type": "function",
                    "function": {
                        "name": "add",
                        "arguments": '{"a": 7, "b": 5}',
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 11, "completion_tokens": 3},
    })

    result = await providers.OpenAIProvider("key", "gpt-test").chat(
        MESSAGES,
        tools=[ADD_TOOL],
        tool_choice={"name": "add"},
        temperature=0,
    )

    body = fake.requests[0]["json"]
    assert body["tools"] == [{
        "type": "function",
        "function": {
            "name": "add",
            "description": "Return a + b.",
            "parameters": ADD_TOOL["input_schema"],
        },
    }]
    assert body["tool_choice"] == {"type": "function", "function": {"name": "add"}}
    assert result["tool_calls"] == [{
        "id": "call_openai",
        "name": "add",
        "arguments": {"a": 7, "b": 5},
    }]
    assert result["stop_reason"] == "tool_use"
    assert result["tool_call_dialect"] == "native"


@pytest.mark.asyncio
async def test_anthropic_translates_tools_and_normalizes_tool_calls(monkeypatch):
    fake = install_fake_http(monkeypatch, {
        "content": [{
            "type": "tool_use",
            "id": "toolu_123",
            "name": "add",
            "input": {"a": 7, "b": 5},
        }],
        "usage": {"input_tokens": 9, "output_tokens": 2},
        "stop_reason": "tool_use",
    })

    result = await providers.AnthropicProvider("key", "claude-test").chat(
        MESSAGES,
        tools=[ADD_TOOL],
        tool_choice={"name": "add"},
        temperature=0,
    )

    body = fake.requests[0]["json"]
    assert body["tools"] == [{
        "name": "add",
        "description": "Return a + b.",
        "input_schema": ADD_TOOL["input_schema"],
    }]
    assert body["tool_choice"] == {"type": "tool", "name": "add"}
    assert result["tool_calls"] == [{
        "id": "toolu_123",
        "name": "add",
        "arguments": {"a": 7, "b": 5},
    }]
    assert result["stop_reason"] == "tool_use"
    assert result["tool_call_dialect"] == "native"


@pytest.mark.asyncio
async def test_anthropic_translates_structured_output_to_native_output_config(
    monkeypatch,
):
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "integer"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    fake = install_fake_http(monkeypatch, {
        "content": [{"type": "text", "text": '{"answer": 12}'}],
        "usage": {"input_tokens": 9, "output_tokens": 4},
        "stop_reason": "end_turn",
    })

    result = await providers.AnthropicProvider("key", "claude-test").chat(
        MESSAGES,
        tools=[ADD_TOOL],
        tool_choice="auto",
        response_format={
            "type": "json_schema",
            "schema": schema,
            "name": "answer",
            "strict": True,
        },
        temperature=0,
    )

    body = fake.requests[0]["json"]
    assert body["output_config"] == {
        "format": {
            "type": "json_schema",
            "schema": schema,
        }
    }
    assert body["tools"][0]["name"] == "add"
    assert body["tool_choice"] == {"type": "auto"}
    assert result["text"] == '{"answer": 12}'
    assert result["tool_calls"] == []


def test_anthropic_schema_cleaning_preserves_original_constraints_for_validation():
    schema = {
        "type": "object",
        "properties": {
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "labels": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
            },
        },
        "required": ["confidence", "labels"],
    }

    cleaned = providers._anthropic_clean_schema(schema)

    confidence = cleaned["properties"]["confidence"]
    labels = cleaned["properties"]["labels"]
    assert "minimum" not in confidence
    assert "maximum" not in confidence
    assert "greater than or equal to 0" in confidence["description"]
    assert "less than or equal to 1" in confidence["description"]
    assert "minItems" not in labels
    assert "at least 1 item" in labels["description"]
    assert "minLength" not in labels["items"]
    assert "at least 1" in labels["items"]["description"]
    assert cleaned["additionalProperties"] is False

    # The gateway still validates provider text against this untouched schema.
    assert schema["properties"]["confidence"]["minimum"] == 0
    assert schema["properties"]["confidence"]["maximum"] == 1
    assert schema["properties"]["labels"]["minItems"] == 1


@pytest.mark.asyncio
async def test_anthropic_rejects_schema_less_structured_output() -> None:
    with pytest.raises(
        providers.ProviderError,
        match="requires a JSON schema",
    ) as error:
        await providers.AnthropicProvider("key", "claude-test").chat(
            MESSAGES,
            response_format={"type": "json_object"},
            temperature=0,
        )

    assert error.value.status == 400
    assert error.value.retryable is False


@pytest.mark.asyncio
async def test_gemini_translates_tools_and_normalizes_tool_calls(monkeypatch):
    fake = install_fake_http(monkeypatch, {
        "candidates": [{
            "content": {"parts": [{
                "functionCall": {"name": "add", "args": {"a": 7, "b": 5}},
                "thoughtSignature": "sig-1",
            }]},
            "finishReason": "STOP",
        }],
        "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 2},
    })

    result = await providers.GeminiProvider("key", "gemini-test", cache_store=None).chat(
        MESSAGES,
        tools=[ADD_TOOL],
        tool_choice={"name": "add"},
        temperature=0,
    )

    body = fake.requests[0]["json"]
    assert body["tools"] == [{
        "function_declarations": [{
            "name": "add",
            "description": "Return a + b.",
            "parameters": ADD_TOOL["input_schema"],
        }],
    }]
    assert body["toolConfig"] == {"function_calling_config": {"mode": "ANY"}}
    assert result["tool_calls"][0]["name"] == "add"
    assert result["tool_calls"][0]["arguments"] == {"a": 7, "b": 5}
    assert result["tool_calls"][0]["id"].startswith("call_")
    assert result["tool_calls"][0]["provider_meta"] == {"thoughtSignature": "sig-1"}
    assert result["stop_reason"] == "tool_use"
    assert result["tool_call_dialect"] == "native"


@pytest.mark.asyncio
async def test_ollama_native_tools_translate_and_normalize_tool_calls(monkeypatch):
    fake = install_fake_http(monkeypatch, {
        "message": {
            "content": "",
            "tool_calls": [{
                "id": "call_ollama",
                "function": {
                    "name": "add",
                    "arguments": '{"a": 7, "b": 5}',
                },
            }],
        },
        "prompt_eval_count": 7,
        "eval_count": 1,
    })

    result = await providers.OllamaProvider("llama3.1").chat(
        MESSAGES,
        tools=[ADD_TOOL],
        tool_choice="auto",
        temperature=0,
    )

    body = fake.requests[0]["json"]
    assert body["think"] is False
    assert body["tools"] == [{
        "type": "function",
        "function": {
            "name": "add",
            "description": "Return a + b.",
            "parameters": ADD_TOOL["input_schema"],
        },
    }]
    assert result["tool_calls"] == [{
        "id": "call_ollama",
        "name": "add",
        "arguments": {"a": 7, "b": 5},
    }]
    assert result["stop_reason"] == "tool_use"
    assert result["tool_call_dialect"] == "native"


@pytest.mark.asyncio
async def test_ollama_prompted_fallback_parses_tool_call(monkeypatch):
    fake = install_fake_http(monkeypatch, {
        "message": {
            "content": '{"tool_call":{"name":"add","arguments":{"a":7,"b":5}}}',
        },
        "prompt_eval_count": 7,
        "eval_count": 1,
    })

    result = await providers.OllamaProvider("gemma4:12b").chat(
        MESSAGES,
        tools=[ADD_TOOL],
        tool_choice="auto",
        temperature=0,
    )

    body = fake.requests[0]["json"]
    assert "tools" not in body
    assert body["messages"][0]["role"] == "system"
    assert "When you need to call a tool" in body["messages"][0]["content"]
    assert result["text"] == ""
    assert result["tool_calls"][0]["name"] == "add"
    assert result["tool_calls"][0]["arguments"] == {"a": 7, "b": 5}
    assert result["tool_calls"][0]["id"].startswith("call_")
    assert result["stop_reason"] == "tool_use"
    assert result["tool_call_dialect"] == "prompted_fallback"


@pytest.mark.asyncio
async def test_ollama_length_stop_is_normalized_to_max_tokens(monkeypatch):
    install_fake_http(monkeypatch, {
        "message": {"content": '{"has_second_topic":'},
        "prompt_eval_count": 7,
        "eval_count": 16,
        "done_reason": "length",
    })

    result = await providers.OllamaProvider("phi4:14b-q4_K_M").chat(
        MESSAGES,
        max_tokens=16,
        temperature=0,
    )

    assert result["stop_reason"] == "max_tokens"


def test_canonical_tool_turns_translate_back_to_provider_message_shapes():
    tool_call = {"id": "call_1", "name": "add", "arguments": {"a": 7, "b": 5}}
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [tool_call]},
        {"role": "tool", "tool_call_id": "call_1", "tool_name": "add", "content": '{"result": 12}'},
    ]

    openai_messages = providers.OpenAIProvider("key", "gpt-test")._translate_messages(messages, "")
    assert openai_messages == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "add", "arguments": '{"a": 7, "b": 5}'},
            }],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"result": 12}'},
    ]

    anthropic_messages = providers.AnthropicProvider("key", "claude-test")._translate_messages(messages)
    assert anthropic_messages == [
        {
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": "call_1",
                "name": "add",
                "input": {"a": 7, "b": 5},
            }],
        },
        {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": "call_1",
                "content": [{"type": "text", "text": '{"result": 12}'}],
            }],
        },
    ]

    gemini_messages = providers.GeminiProvider("key", "gemini-test", cache_store=None)._translate_messages(messages)
    assert gemini_messages == [
        {
            "role": "model",
            "parts": [{"functionCall": {"name": "add", "args": {"a": 7, "b": 5}}}],
        },
        {
            "role": "user",
            "parts": [{
                "function_response": {
                    "name": "add",
                    "response": {"result": 12},
                },
            }],
        },
    ]
