import json
import unittest

from advisor_gateway import CompletionRequest, CompletionResponse, serialize_transcript


class SerializerTests(unittest.TestCase):
    def test_preserves_order_and_partial_turn(self) -> None:
        request = CompletionRequest(
            model="executor",
            system="system",
            tools=({"name": "lookup", "input_schema": {"type": "object"}},),
            messages=(
                {"role": "user", "content": ({"type": "text", "text": "α"},)},
                {
                    "role": "assistant",
                    "content": ({"type": "tool_use", "id": "t1", "name": "lookup"},),
                },
                {"role": "user", "content": ({"type": "tool_result", "tool_use_id": "t1"},)},
            ),
        )
        response = CompletionResponse(
            content=(
                {"type": "text", "text": "partial"},
                {"type": "tool_use", "id": "a1", "name": "advisor", "input": {}},
            ),
            stop_reason="tool_use",
        )

        rendered = serialize_transcript(request, response)
        payload = rendered.split("\n", 1)[1].rsplit("\n", 1)[0]
        decoded = json.loads(payload)

        self.assertEqual(decoded["messages"][0]["content"][0]["text"], "α")
        self.assertEqual(decoded["messages"][2]["content"][0]["tool_use_id"], "t1")
        self.assertEqual(decoded["partial_current_turn"]["content"][0]["text"], "partial")
        self.assertIn(f'bytes="{len(payload.encode("utf-8"))}"', rendered.splitlines()[0])

    def test_rejects_non_json_values(self) -> None:
        request = CompletionRequest(model="x", messages=({"role": "user", "content": object()},))
        with self.assertRaisesRegex(TypeError, "non-JSON"):
            serialize_transcript(request)
