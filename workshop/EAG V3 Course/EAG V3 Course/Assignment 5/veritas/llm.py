"""Provider-agnostic LLM client.

Anthropic is preferred. OpenAI is supported because that is the key this
project was developed against; the skill contracts are identical either way.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    # Cache counters: if `cache_read` stays 0 across a run, the prefix is being
    # invalidated somewhere and the two-block system prompt is buying nothing.
    cache_read: int = 0
    cache_write: int = 0

    def __iadd__(self, other: "Usage") -> "Usage":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read += other.cache_read
        self.cache_write += other.cache_write
        return self


def _strip_fences(text: str) -> str:
    """Models sometimes wrap JSON in ```json fences despite instructions."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return fenced.group(1).strip() if fenced else text.strip()


def parse_json(text: str) -> dict[str, Any]:
    """Parse a model response into JSON, tolerating fences and leading prose."""
    candidate = _strip_fences(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # Last resort: grab the outermost {...} span.
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        raise LLMError(f"no JSON object in response: {text[:300]!r}")
    return json.loads(candidate[start : end + 1])


class LLM:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.max_tokens = cfg.get("max_tokens", 8000)
        self.usage = Usage()

        if os.environ.get("ANTHROPIC_API_KEY"):
            import anthropic

            self.provider = "anthropic"
            self.model = cfg["anthropic"]
            self._client = anthropic.Anthropic()
        elif os.environ.get("OPENAI_API_KEY"):
            from openai import OpenAI

            self.provider = "openai"
            self.model = cfg["openai"]
            self._client = OpenAI()
        else:
            raise LLMError(
                "No API key found. Set ANTHROPIC_API_KEY (preferred) or OPENAI_API_KEY."
            )

    def complete(self, system: str | list[str], user: str) -> tuple[dict[str, Any], str]:
        """Return (parsed_json, raw_text). Raises LLMError on unusable output.

        `system` may be a list of blocks. Caching is a prefix match, so keeping
        the invariant master prompt as its own leading block lets every skill
        read the same cache entry instead of each skill writing its own copy of
        master+contract. Max 4 breakpoints per request.
        """
        blocks = [system] if isinstance(system, str) else list(system)
        if self.provider == "anthropic":
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "adaptive"},
                system=[{"type": "text", "text": text,
                         "cache_control": {"type": "ephemeral"}}
                        for text in blocks[:4]] + [
                    {"type": "text", "text": text} for text in blocks[4:]
                ],
                messages=[{"role": "user", "content": user}],
            )
            raw = "".join(b.text for b in resp.content if b.type == "text")
            self.usage += Usage(
                resp.usage.input_tokens,
                resp.usage.output_tokens,
                getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
                getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
            )
        else:
            resp = self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "\n\n---\n\n".join(blocks)},
                    {"role": "user", "content": user},
                ],
            )
            raw = resp.choices[0].message.content or ""
            if resp.usage:
                self.usage += Usage(
                    resp.usage.prompt_tokens, resp.usage.completion_tokens
                )

        if not raw.strip():
            raise LLMError("empty response from model")
        return parse_json(raw), raw
