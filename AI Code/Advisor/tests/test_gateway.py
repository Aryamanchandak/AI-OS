import unittest

from advisor_gateway import (
    AdvisorConfig,
    AdvisorGateway,
    AdvisorLimitError,
    AdvisorResponseError,
    CompletionRequest,
    CompletionResponse,
    TokenUsage,
)


class QueueProvider:
    def __init__(self, *responses: CompletionResponse) -> None:
        self.responses = list(responses)
        self.requests: list[CompletionRequest] = []

    async def __call__(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Unexpected provider call")
        return self.responses.pop(0)


def call_response(call_id: str = "a1") -> CompletionResponse:
    return CompletionResponse(
        content=(
            {"type": "text", "text": "Working."},
            {"type": "tool_use", "id": call_id, "name": "advisor", "input": {}},
        ),
        stop_reason="tool_use",
        usage=TokenUsage(10, 2),
    )


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_intercepts_and_returns_advice_mid_request(self) -> None:
        final = CompletionResponse(
            content=({"type": "text", "text": "Final"},),
            usage=TokenUsage(12, 3),
        )
        executor = QueueProvider(call_response(), final)
        advisor = QueueProvider(
            CompletionResponse(
                content=(
                    {"type": "thinking", "thinking": "hidden"},
                    {"type": "text", "text": "Check the invariant."},
                ),
                usage=TokenUsage(20, 4),
            )
        )
        gateway = AdvisorGateway(executor, advisor, AdvisorConfig("strong"))

        result = await gateway.run(
            CompletionRequest("cheap", ({"role": "user", "content": "solve"},)),
            request_id="r1",
        )

        self.assertEqual(result.response, final)
        self.assertEqual([item.role for item in result.usage.iterations], ["executor", "advisor", "executor"])
        self.assertEqual(result.usage.total.input_tokens, 42)
        first_request = executor.requests[0]
        self.assertEqual(first_request.tools[-1]["input_schema"]["properties"], {})
        self.assertIn("advisor tool", first_request.system)
        self.assertEqual(advisor.requests[0].tools, ())
        self.assertEqual(advisor.requests[0].max_tokens, 2048)
        tool_result = executor.requests[1].messages[-1]["content"][0]
        self.assertEqual(tool_result["content"], "Check the invariant.")
        self.assertNotIn("hidden", tool_result["content"])

    async def test_dummy_input_compatibility_schema(self) -> None:
        executor = QueueProvider(CompletionResponse(content=({"type": "text", "text": "done"},)))
        gateway = AdvisorGateway(
            executor,
            QueueProvider(),
            AdvisorConfig("strong", dummy_input_field="placeholder"),
        )
        await gateway.run(CompletionRequest("cheap", ()))
        schema = executor.requests[0].tools[-1]["input_schema"]
        self.assertEqual(schema["required"], ["placeholder"])

    async def test_mixed_tool_calls_are_passed_through(self) -> None:
        mixed = CompletionResponse(
            content=(
                {"type": "tool_use", "id": "a", "name": "advisor", "input": {}},
                {"type": "tool_use", "id": "b", "name": "lookup", "input": {}},
            )
        )
        advisor = QueueProvider()
        result = await AdvisorGateway(
            QueueProvider(mixed), advisor, AdvisorConfig("strong")
        ).run(CompletionRequest("cheap", ()))
        self.assertEqual(result.response, mixed)
        self.assertEqual(advisor.requests, [])

    async def test_limit_feedback_then_repeated_call_raises(self) -> None:
        executor = QueueProvider(call_response("a1"), call_response("a2"))
        gateway = AdvisorGateway(executor, QueueProvider(), AdvisorConfig("strong", max_uses=0))
        with self.assertRaises(AdvisorLimitError):
            await gateway.run(CompletionRequest("cheap", ()))
        feedback = executor.requests[1].messages[-1]["content"][0]["content"]
        self.assertIn("budget exhausted", feedback)

    async def test_existing_advisor_tool_is_rejected(self) -> None:
        gateway = AdvisorGateway(QueueProvider(), QueueProvider(), AdvisorConfig("strong"))
        request = CompletionRequest("cheap", (), tools=({"name": "advisor"},))
        with self.assertRaisesRegex(ValueError, "already defines"):
            await gateway.run(request)

    async def test_duplicate_advisor_calls_share_one_consultation(self) -> None:
        duplicate = CompletionResponse(
            content=(
                {"type": "tool_use", "id": "a1", "name": "advisor", "input": {}},
                {"type": "tool_use", "id": "a2", "name": "advisor", "input": {}},
            )
        )
        final = CompletionResponse(content=({"type": "text", "text": "done"},))
        executor = QueueProvider(duplicate, final)
        advisor = QueueProvider(
            CompletionResponse(content=({"type": "text", "text": "one review"},))
        )

        result = await AdvisorGateway(executor, advisor, AdvisorConfig("strong")).run(
            CompletionRequest("cheap", ())
        )

        self.assertEqual(len(advisor.requests), 1)
        self.assertEqual([item.role for item in result.usage.iterations], ["executor", "advisor", "executor"])
        results = executor.requests[1].messages[-1]["content"]
        self.assertEqual([item["tool_use_id"] for item in results], ["a1", "a2"])
        self.assertEqual({item["content"] for item in results}, {"one review"})

    async def test_rejects_nonempty_input_for_empty_contract(self) -> None:
        bad = CompletionResponse(
            content=({"type": "tool_use", "id": "a", "name": "advisor", "input": {"why": "x"}},)
        )
        with self.assertRaisesRegex(ValueError, "must be empty"):
            await AdvisorGateway(QueueProvider(bad), QueueProvider(), AdvisorConfig("strong")).run(
                CompletionRequest("cheap", ())
            )

    async def test_validates_dummy_input_contract(self) -> None:
        call = CompletionResponse(
            content=(
                {
                    "type": "tool_use",
                    "id": "a",
                    "name": "advisor",
                    "input": {"placeholder": ""},
                },
            )
        )
        final = CompletionResponse(content=({"type": "text", "text": "done"},))
        advisor = QueueProvider(CompletionResponse(content=({"type": "text", "text": "advice"},)))
        await AdvisorGateway(
            QueueProvider(call, final),
            advisor,
            AdvisorConfig("strong", dummy_input_field="placeholder"),
        ).run(CompletionRequest("cheap", ()))
        self.assertEqual(len(advisor.requests), 1)

    async def test_empty_advisor_text_is_an_error(self) -> None:
        advisor = QueueProvider(CompletionResponse(content=({"type": "thinking", "thinking": "x"},)))
        with self.assertRaisesRegex(AdvisorResponseError, "no textual guidance"):
            await AdvisorGateway(
                QueueProvider(call_response()), advisor, AdvisorConfig("strong")
            ).run(CompletionRequest("cheap", ()))
