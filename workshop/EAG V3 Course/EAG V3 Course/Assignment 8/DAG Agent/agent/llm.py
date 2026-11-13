"""Direct Anthropic SDK adapter; no gateway or shared AI OS services."""

import os
import threading
from typing import Protocol


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class AnthropicLLM:
    def __init__(self, api_key=None, model="claude-sonnet-4-6", client=None,
                 max_tokens=8192):
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=180.0, max_retries=2)
        self.client, self.model, self.max_tokens = client, model, max_tokens
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
        self._lock = threading.Lock()

    def complete(self, system, user):
        try:
            message = self.client.messages.create(
                model=self.model, system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            detail = f"HTTP {status}" if status else type(exc).__name__
            raise RuntimeError(f"Model provider call failed ({detail}); check .env credentials and model access") from None
        with self._lock:
            self.usage["calls"] += 1
            for key in ("input_tokens", "output_tokens"):
                self.usage[key] += int(getattr(message.usage, key, 0) or 0)
        if message.stop_reason == "max_tokens":
            raise RuntimeError("Model output was truncated; no partial result accepted")
        if message.stop_reason not in {"end_turn", "stop_sequence"}:
            raise RuntimeError("Model did not return a complete text answer")
        text = "".join(block.text for block in message.content if block.type == "text")
        if not text.strip():
            raise RuntimeError("Model returned an empty answer")
        return text


def build_llm(config, mock=False, session=None):
    if mock:
        from agent.mock_llm import MockLLM
        return MockLLM()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is missing. Add it to this project's .env and use ./compare; "
                         "supplied-evidence comparisons need no API key.")
    model = os.getenv("ANTHROPIC_MODEL", config.get("model", "claude-sonnet-4-6"))
    return AnthropicLLM(api_key=key, model=model)
