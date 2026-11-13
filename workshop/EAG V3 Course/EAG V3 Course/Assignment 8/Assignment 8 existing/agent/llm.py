"""Claude client wrapper.

Single place that knows about the Anthropic SDK. Everything else takes a
`complete(system, user) -> str` callable, which is what makes --mock possible.
"""

from __future__ import annotations

import os
from typing import Protocol


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class ClaudeLLM:
    def __init__(self, model: str = "claude-opus-4-8", effort: str = "high"):
        import anthropic  # imported lazily so --mock runs without the SDK

        self._client = anthropic.Anthropic()
        self._model = model
        self._effort = effort

    def complete(self, system: str, user: str) -> str:
        # Streaming: max_tokens is high enough that a non-streaming request
        # risks an SDK HTTP timeout.
        with self._client.messages.stream(
            model=self._model,
            max_tokens=32000,
            thinking={"type": "adaptive"},
            output_config={"effort": self._effort},
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()

        if message.stop_reason == "refusal":
            raise RuntimeError(f"Claude refused: {message.stop_details}")

        return "".join(b.text for b in message.content if b.type == "text")


def build_llm(config: dict, mock: bool = False) -> LLM:
    if mock:
        from agent.mock_llm import MockLLM

        return MockLLM()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Export it, or run with --mock to "
            "exercise the architecture with a scripted planner."
        )
    return ClaudeLLM(config.get("model", "claude-opus-4-8"), config.get("effort", "high"))
