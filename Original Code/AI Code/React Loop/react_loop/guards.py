"""Component 3.7 — guards (spine).

Small, independent safety rails the loop consults. None of them reason; they are
mechanical checks that keep a text-driven loop from misbehaving:

    - max-iteration cap ....... owned by the loop's counter (config.max_iterations).
    - repeat-action detection . same tool + same args twice in a row -> intervene.
    - observation truncation .. cap oversized tool output before it enters context.

Error handling philosophy (enforced in mcp_client + loop, documented here): a
tool raising becomes an observation, never a crash. Tool failure is normal
control flow.
"""

from __future__ import annotations

import json
from typing import Any


def truncate_observation(text: str, char_limit: int) -> str:
    """Cap an observation so a huge tool output can't blow the context window."""
    # char_limit <= 0 is the "disabled" sentinel; short-enough text passes through.
    if char_limit <= 0 or len(text) <= char_limit:
        return text
    omitted = len(text) - char_limit
    # Keep the head (usually the most relevant part) and tell the model exactly
    # how much was dropped, so it knows the observation is incomplete.
    return (
        text[:char_limit]
        + f"\n\n...[observation truncated: {omitted} more characters omitted]"
    )


def _fingerprint(tool: str, tool_input: dict[str, Any]) -> str:
    """Stable signature of an action, order-independent for the args."""
    # sort_keys makes {"a":1,"b":2} and {"b":2,"a":1} hash identical, so a repeat
    # is caught regardless of key ordering the model happens to emit.
    return tool + "::" + json.dumps(tool_input, sort_keys=True, ensure_ascii=False)


class RepeatGuard:
    """Detects the same (tool, args) being chosen twice in a row.

    Consecutive identical actions mean the model is stuck — re-running an
    identical call will only re-produce the identical observation. We nudge it
    to change course rather than let it spin against the iteration cap.
    """

    def __init__(self) -> None:
        # Fingerprint of the previous action; None before the first action.
        self._last: str | None = None

    def is_repeat(self, tool: str, tool_input: dict[str, Any]) -> bool:
        # Compare against the immediately-preceding action only (consecutive
        # repeats), then remember this one for the next call. Non-consecutive
        # revisits are allowed — they can be legitimate re-checks.
        fp = _fingerprint(tool, tool_input)
        repeat = fp == self._last
        self._last = fp
        return repeat

    @staticmethod
    def message(tool: str) -> str:
        return (
            f"GUARD: you just called '{tool}' with identical arguments as the "
            "previous step, which produced the same observation. Do not repeat "
            "it. Either use the result you already have, try different "
            "arguments/tool, or give your final_answer."
        )
