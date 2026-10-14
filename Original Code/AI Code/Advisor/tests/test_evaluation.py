import unittest

from advisor_gateway import (
    AdvisorConfig,
    CompletionRequest,
    CompletionResponse,
    EvalArm,
    EvalHarness,
    EvalTask,
)


class EchoProvider:
    def __init__(self, label: str) -> None:
        self.label = label
        self.requests = []

    async def __call__(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        return CompletionResponse(content=({"type": "text", "text": self.label},))


class EvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_three_arms(self) -> None:
        executor = EchoProvider("executor")
        advisor = EchoProvider("advisor")
        harness = EvalHarness(executor, advisor, AdvisorConfig("strong"))
        task = EvalTask(
            "sample",
            CompletionRequest("cheap", ({"role": "user", "content": "task"},)),
            lambda response: 1.0 if response.content[0]["text"] else 0.0,
        )

        results = await harness.run((task,))

        self.assertEqual([result.arm for result in results], list(EvalArm))
        self.assertTrue(all(result.score == 1.0 for result in results))
        self.assertEqual(advisor.requests[-1].model, "strong")
        self.assertEqual(advisor.requests[-1].tools, ())
