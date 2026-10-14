"""Recovery classifier.

When the Critic fails a node, this maps the failure to a recovery strategy.
It is a pure function over (verdict, reason, node) -> Recovery, deliberately
free of LLM calls and I/O so it stays unit-testable.

Its unit tests (tests/test_recovery.py) must keep passing after any change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Strategy(str, Enum):
    RETRY_PRODUCER = "retry_producer"      # transient / empty output — just rerun
    REFETCH_UPSTREAM = "refetch_upstream"  # data was missing or stale — refetch it
    RECOMPUTE = "recompute"                # arithmetic wrong — rerun via Coder
    REGROUND = "reground"                  # claims unsupported by data — reground text
    ESCALATE = "escalate"                  # cannot be repaired automatically


@dataclass(frozen=True)
class Recovery:
    strategy: Strategy
    reason: str


# Ordered most-specific first; the first matching rule wins.
_RULES: list[tuple[Strategy, re.Pattern[str]]] = [
    (Strategy.REFETCH_UPSTREAM, re.compile(
        r"\b(stale|missing data|no data|empty series|incomplete (?:data|series)|"
        r"insufficient (?:data|history)|fewer than)\b", re.I)),
    (Strategy.RECOMPUTE, re.compile(
        r"\b(arithmetic|does not sum|doesn'?t sum|sums? to|miscalculat\w*|"
        r"off by|weights?|rounding|math error)\b", re.I)),
    (Strategy.REGROUND, re.compile(
        r"\b(unsupported|not (?:present|found) in|hallucinat\w*|fabricat\w*|"
        r"cannot be traced|no source|ungrounded)\b", re.I)),
    (Strategy.RETRY_PRODUCER, re.compile(
        r"\b(timeout|timed out|transient|truncated|empty output|malformed|"
        r"parse error)\b", re.I)),
]


def classify(verdict: str, reason: str) -> Recovery:
    """Classify a Critic verdict into a recovery strategy.

    `verdict` is "pass" or "fail". A passing verdict never yields a recovery.
    """
    if verdict.strip().lower() == "pass":
        raise ValueError("classify() called on a passing verdict")

    text = (reason or "").strip()
    if not text:
        return Recovery(Strategy.ESCALATE, "critic failed without a reason")

    for strategy, pattern in _RULES:
        if pattern.search(text):
            return Recovery(strategy, text)

    return Recovery(Strategy.ESCALATE, text)


def recovery_instruction(recovery: Recovery, original_input: str) -> str:
    """The instruction handed back to the Planner when splicing a fix."""
    guidance = {
        Strategy.RETRY_PRODUCER:
            "The previous attempt failed transiently. Re-run the same work.",
        Strategy.REFETCH_UPSTREAM:
            "Upstream data was missing or stale. Re-fetch the source data "
            "first, then redo the work on the fresh data.",
        Strategy.RECOMPUTE:
            "The numbers were wrong. Recompute every figure with the coder "
            "skill; do not restate any number you did not compute.",
        Strategy.REGROUND:
            "Claims were not supported by the retrieved data. Rebuild the "
            "answer using only figures that appear in the upstream outputs.",
        Strategy.ESCALATE:
            "Automatic recovery is not possible. State the limitation plainly "
            "in the answer rather than guessing.",
    }[recovery.strategy]

    return (
        f"{guidance}\n\n"
        f"Critic's finding: {recovery.reason}\n\n"
        f"Original task: {original_input}"
    )
