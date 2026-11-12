import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import AsyncMock, patch

from advisor_gateway import (
    CompletionResponse,
    GatewayResult,
    GatewayUsage,
    IterationUsage,
    ProviderError,
    TokenUsage,
)
from advisor_gateway.cli import build_parser, main


def sample_result() -> GatewayResult:
    return GatewayResult(
        CompletionResponse(
            content=({"type": "text", "text": "final answer"},),
            stop_reason="end_turn",
            usage=TokenUsage(4, 2),
        ),
        GatewayUsage((IterationUsage(1, "executor", "cheap", TokenUsage(4, 2)),)),
        "request-1",
    )


BASE_ARGS = [
    "run",
    "--executor-model",
    "cheap",
    "--advisor-model",
    "strong",
    "--advisor-base-url",
    "https://advisor.example/v1",
]


class CliTests(unittest.TestCase):
    def test_help_names_run_command(self) -> None:
        output = io.StringIO()
        with self.assertRaises(SystemExit) as caught, redirect_stdout(output):
            build_parser().parse_args(["--help"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("run", output.getvalue())

    def test_prompt_and_stdin_flags_are_exclusive(self) -> None:
        errors = io.StringIO()
        with self.assertRaises(SystemExit) as caught, redirect_stderr(errors):
            build_parser().parse_args(BASE_ARGS + ["--prompt", "x", "--stdin"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("not allowed with argument", errors.getvalue())

    def test_prompt_prints_plain_final_text(self) -> None:
        output = io.StringIO()
        with patch("advisor_gateway.cli._run", AsyncMock(return_value=sample_result())) as run:
            with redirect_stdout(output):
                status = main(BASE_ARGS + ["--prompt", "solve"])
        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue(), "final answer\n")
        self.assertEqual(run.await_args.args[1], "solve")

    def test_reads_stdin_and_emits_json(self) -> None:
        output = io.StringIO()
        with (
            patch("advisor_gateway.cli.sys.stdin", io.StringIO("from pipe")),
            patch("advisor_gateway.cli._run", AsyncMock(return_value=sample_result())) as run,
            redirect_stdout(output),
        ):
            status = main(BASE_ARGS + ["--json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(run.await_args.args[1], "from pipe")
        self.assertEqual(payload["response"]["text"], "final answer")
        self.assertEqual(payload["usage"]["total"]["input_tokens"], 4)

    def test_provider_error_goes_to_stderr_without_key(self) -> None:
        errors = io.StringIO()
        with (
            patch("advisor_gateway.cli._run", AsyncMock(side_effect=ProviderError("safe failure"))),
            redirect_stderr(errors),
        ):
            status = main(BASE_ARGS + ["--prompt", "x", "--advisor-api-key", "very-secret"])
        self.assertEqual(status, 2)
        self.assertEqual(errors.getvalue(), "error: safe failure\n")
        self.assertNotIn("very-secret", errors.getvalue())

    def test_missing_required_configuration_is_nonzero(self) -> None:
        errors = io.StringIO()
        with redirect_stderr(errors):
            status = main(["run", "--prompt", "x"])
        self.assertEqual(status, 2)
        self.assertIn("executor model is required", errors.getvalue())
