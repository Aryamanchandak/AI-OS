import json
import socket
import unittest
import urllib.error
from unittest.mock import patch

from advisor_gateway import (
    AdvisorConfig,
    AdvisorGateway,
    CompletionRequest,
    OpenAICompatibleProvider,
    ProviderError,
)
from advisor_gateway.openai_compatible import request_to_openai, response_from_openai


class AdapterMappingTests(unittest.TestCase):
    def test_maps_request_text_tools_calls_and_results(self) -> None:
        request = CompletionRequest(
            "model-a",
            (
                {"role": "user", "content": ({"type": "text", "text": "hello"},)},
                {
                    "role": "assistant",
                    "content": (
                        {"type": "text", "text": "checking"},
                        {"type": "tool_use", "id": "t1", "name": "lookup", "input": {"q": "α"}},
                    ),
                },
                {"role": "user", "content": ({"type": "tool_result", "tool_use_id": "t1", "content": "ok"},)},
            ),
            system="system",
            tools=({"name": "lookup", "description": "find", "input_schema": {"type": "object"}},),
            max_tokens=25,
        )

        payload = request_to_openai(request)

        self.assertFalse(payload["stream"])
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "system"})
        self.assertEqual(payload["messages"][2]["tool_calls"][0]["function"]["arguments"], '{"q":"α"}')
        self.assertEqual(payload["messages"][3]["role"], "tool")
        self.assertEqual(payload["tools"][0]["function"]["parameters"], {"type": "object"})

    def test_maps_response_arguments_usage_and_finish_reason(self) -> None:
        response = response_from_openai(
            {
                "id": "c1",
                "model": "m",
                "choices": [
                    {
                        "message": {
                            "content": "working",
                            "tool_calls": [
                                {
                                    "id": "a1",
                                    "type": "function",
                                    "function": {"name": "advisor", "arguments": "{}"},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 9,
                    "completion_tokens": 3,
                    "prompt_tokens_details": {"cached_tokens": 2},
                },
            }
        )
        self.assertEqual(response.stop_reason, "tool_use")
        self.assertEqual(response.content[1]["input"], {})
        self.assertEqual(response.usage.input_tokens, 9)
        self.assertEqual(response.usage.cache_read_tokens, 2)
        self.assertEqual(response.provider_metadata["finish_reason"], "tool_calls")

    def test_rejects_malformed_shapes_and_arguments(self) -> None:
        with self.assertRaisesRegex(ProviderError, "completion choice"):
            response_from_openai({"choices": []})
        with self.assertRaisesRegex(ProviderError, "malformed JSON"):
            response_from_openai(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {"id": "x", "function": {"name": "f", "arguments": "{"}}
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            )

    def test_rejects_non_json_tool_arguments(self) -> None:
        request = CompletionRequest(
            "m",
            (
                {
                    "role": "assistant",
                    "content": (
                        {"type": "tool_use", "id": "x", "name": "f", "input": {"x": object()}},
                    ),
                },
            ),
        )
        with self.assertRaisesRegex(ProviderError, "only JSON values"):
            request_to_openai(request)
        with self.assertRaisesRegex(ProviderError, "decode to an object"):
            response_from_openai(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {"id": "x", "function": {"name": "f", "arguments": "[]"}}
                                ]
                            }
                        }
                    ]
                }
            )


class _FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return self.body


class AdapterHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_posts_through_openai_http_boundary(self) -> None:
        response_body = json.dumps(
            {"choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}], "usage": {}}
        ).encode()
        seen = []

        def fake_urlopen(request, timeout):
            seen.append((request, timeout))
            return _FakeHttpResponse(response_body)

        provider = OpenAICompatibleProvider("http://127.0.0.1:11434/v1", api_key="secret")
        with patch("urllib.request.urlopen", fake_urlopen):
            response = await provider(CompletionRequest("m", ({"role": "user", "content": "hi"},)))
        self.assertEqual(response.content[0]["text"], "hello")
        request = seen[0][0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/v1/chat/completions")
        self.assertEqual(json.loads(request.data)["model"], "m")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    async def test_http_error_is_sanitized(self) -> None:
        error = urllib.error.HTTPError(
            "https://top-secret.example/v1", 401, "private detail", {}, None
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ProviderError) as caught:
                await OpenAICompatibleProvider("https://advisor.example/v1", api_key="top-secret")(
                    CompletionRequest("m", ())
                )
        message = str(caught.exception)
        self.assertEqual(message, "Provider request failed with HTTP 401")
        self.assertNotIn("secret", message)

    async def test_malformed_json_is_sanitized(self) -> None:
        with patch(
            "urllib.request.urlopen", return_value=_FakeHttpResponse(b"not-json private-data")
        ):
            with self.assertRaisesRegex(ProviderError, "malformed JSON"):
                await OpenAICompatibleProvider("http://localhost/v1")(CompletionRequest("m", ()))

    async def test_timeout_is_sanitized(self) -> None:
        with patch("urllib.request.urlopen", side_effect=socket.timeout("private host detail")):
            with self.assertRaises(ProviderError) as caught:
                await OpenAICompatibleProvider("https://advisor.example/v1")(
                    CompletionRequest("m", ())
                )
        self.assertEqual(str(caught.exception), "Provider request timed out")

    def test_rejects_unsafe_base_urls(self) -> None:
        for url in ("file:///tmp/provider", "https://user:secret@example.com/v1", "not-a-url"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                OpenAICompatibleProvider(url)

    async def test_gateway_end_to_end_through_fake_http_transport(self) -> None:
        requests = []
        executor_calls = 0

        def fake_urlopen(request, timeout):
            nonlocal executor_calls
            payload = json.loads(request.data)
            requests.append((request.full_url, payload))
            if payload["model"] == "cheap":
                executor_calls += 1
                if executor_calls == 1:
                    body = {
                        "choices": [
                            {
                                "message": {
                                    "content": "working",
                                    "tool_calls": [
                                        {
                                            "id": "a1",
                                            "type": "function",
                                            "function": {"name": "advisor", "arguments": "{}"},
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                    }
                else:
                    body = {
                        "choices": [{"message": {"content": "final"}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 8, "completion_tokens": 1},
                    }
            else:
                body = {
                    "choices": [{"message": {"content": "check it"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2},
                }
            return _FakeHttpResponse(json.dumps(body).encode())

        gateway = AdvisorGateway(
            OpenAICompatibleProvider("http://executor.local/v1"),
            OpenAICompatibleProvider("https://advisor.example/v1"),
            AdvisorConfig("strong"),
        )
        with patch("urllib.request.urlopen", fake_urlopen):
            result = await gateway.run(
                CompletionRequest("cheap", ({"role": "user", "content": "solve"},))
            )

        self.assertEqual(result.response.content[0]["text"], "final")
        self.assertEqual([item.role for item in result.usage.iterations], ["executor", "advisor", "executor"])
        self.assertEqual(len(requests), 3)
        tool_result = requests[2][1]["messages"][-1]
        self.assertEqual(tool_result["role"], "tool")
        self.assertEqual(tool_result["content"], "check it")
