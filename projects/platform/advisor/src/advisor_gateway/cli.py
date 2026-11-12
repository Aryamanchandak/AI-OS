from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .accounting import SQLiteIterationStore
from .gateway import AdvisorGateway, AdvisorLimitError, AdvisorResponseError
from .models import AdvisorConfig, CompletionRequest, CompletionResponse, GatewayResult
from .openai_compatible import OpenAICompatibleProvider, ProviderError


ENV_PREFIX = "ADVISOR_GATEWAY_"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="advisor-gateway",
        description="Run an executor model with a stronger advisor model.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run one non-streaming chat completion")
    source = run.add_mutually_exclusive_group()
    source.add_argument("--prompt", help="user prompt; otherwise read standard input")
    source.add_argument("--stdin", action="store_true", help="explicitly read the prompt from stdin")
    run.add_argument("--executor-base-url", default=_env("EXECUTOR_BASE_URL", "http://127.0.0.1:11434/v1"))
    run.add_argument("--advisor-base-url", default=_env("ADVISOR_BASE_URL"))
    run.add_argument("--executor-model", default=_env("EXECUTOR_MODEL"))
    run.add_argument("--advisor-model", default=_env("ADVISOR_MODEL"))
    run.add_argument("--executor-api-key", default=_env("EXECUTOR_API_KEY"), help=argparse.SUPPRESS)
    run.add_argument("--advisor-api-key", default=_env("ADVISOR_API_KEY"), help=argparse.SUPPRESS)
    run.add_argument("--max-uses", type=int, default=_env_int("MAX_USES", 2))
    run.add_argument("--max-tokens", type=int, default=_env_int("MAX_TOKENS", 2048))
    run.add_argument("--dummy-input-field", default=_env("DUMMY_INPUT_FIELD"))
    run.add_argument("--usage-db", type=Path, default=_env("USAGE_DB"))
    run.add_argument("--timeout", type=float, default=_env_float("TIMEOUT", 60.0))
    run.add_argument("--json", action="store_true", help="emit the complete result as JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        if args.command != "run":
            parser.error("a command is required")
        _validate_run_args(args)
        prompt = args.prompt if args.prompt is not None else sys.stdin.read()
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        result = asyncio.run(_run(args, prompt))
        if args.json:
            print(json.dumps(_result_json(result), ensure_ascii=False, sort_keys=True))
        else:
            text = _response_text(result.response)
            if not text:
                raise ValueError("executor returned no final text")
            print(text)
        return 0
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    except (
        AdvisorLimitError,
        AdvisorResponseError,
        ProviderError,
        ValueError,
        OSError,
        sqlite3.Error,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


async def _run(args: argparse.Namespace, prompt: str) -> GatewayResult:
    executor = OpenAICompatibleProvider(
        args.executor_base_url, api_key=args.executor_api_key, timeout=args.timeout
    )
    advisor = OpenAICompatibleProvider(
        args.advisor_base_url, api_key=args.advisor_api_key, timeout=args.timeout
    )
    config = AdvisorConfig(
        args.advisor_model,
        max_uses=args.max_uses,
        max_tokens=args.max_tokens,
        dummy_input_field=args.dummy_input_field,
    )
    recorder = SQLiteIterationStore(args.usage_db) if args.usage_db else None
    gateway = AdvisorGateway(executor, advisor, config, recorder)
    request = CompletionRequest(
        model=args.executor_model,
        messages=({"role": "user", "content": ({"type": "text", "text": prompt},)},),
    )
    return await gateway.run(request)


def _validate_run_args(args: argparse.Namespace) -> None:
    for name, label in (
        ("executor_model", "executor model"),
        ("advisor_model", "advisor model"),
        ("advisor_base_url", "advisor base URL"),
    ):
        value = getattr(args, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} is required (flag or {ENV_PREFIX}{name.upper()})")


def _response_text(response: CompletionResponse) -> str:
    parts = [
        block.get("text")
        for block in response.content
        if block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
    return "\n".join(part for part in parts if part).strip()


def _result_json(result: GatewayResult) -> dict[str, Any]:
    total = result.usage.total
    return {
        "request_id": result.request_id,
        "response": {
            "content": list(result.response.content),
            "stop_reason": result.response.stop_reason,
            "text": _response_text(result.response),
        },
        "usage": {
            "iterations": [
                {
                    "ordinal": item.ordinal,
                    "role": item.role,
                    "model": item.model,
                    "input_tokens": item.usage.input_tokens,
                    "output_tokens": item.usage.output_tokens,
                    "cache_read_tokens": item.usage.cache_read_tokens,
                    "cache_write_tokens": item.usage.cache_write_tokens,
                }
                for item in result.usage.iterations
            ],
            "total": {
                "input_tokens": total.input_tokens,
                "output_tokens": total.output_tokens,
                "cache_read_tokens": total.cache_read_tokens,
                "cache_write_tokens": total.cache_write_tokens,
            },
        },
    }


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"{ENV_PREFIX}{name}", default)


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{ENV_PREFIX}{name} must be an integer") from None


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{ENV_PREFIX}{name} must be a number") from None


if __name__ == "__main__":
    raise SystemExit(main())
