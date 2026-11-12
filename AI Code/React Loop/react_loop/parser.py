"""Component 3.4 — action contract + parser (spine; the heart of the loop).

The model must reply with exactly one JSON object, in one of two shapes:

    {"thought": "...", "tool": "<name>", "tool_input": { ... }}
    {"thought": "...", "final_answer": "..."}

Two failure paths, kept as *distinct* exception types so the loop can handle
each according to the repair behavior documented in README.md:

    MalformedDecision  -> structural failure (bad JSON / wrong shape).
                          The loop RE-ASKS (repair path), bounded by max_repairs.
    UnknownTool        -> well-formed decision naming a tool that doesn't exist.
                          The loop turns it into an OBSERVATION; the model
                          self-corrects on the next turn (NOT a repair, NOT a crash).

Bad *arguments* aren't validated here (we don't ship a JSON-schema validator);
they surface at execution time as an error observation from call_tool, which is
the same "tool failure is normal control flow" path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class DecisionError(Exception):
    """Base for anything wrong with a model decision."""


class MalformedDecision(DecisionError):
    """Structural failure -> triggers the bounded repair path."""


class UnknownTool(DecisionError):
    """Valid shape, unknown tool name -> becomes an observation."""

    def __init__(self, tool: str, available: Iterable[str]) -> None:
        self.tool = tool
        self.available = list(available)
        super().__init__(
            f"Unknown tool '{tool}'. Available tools: "
            f"{', '.join(self.available) or '(none)'}."
        )


@dataclass(frozen=True)
class Decision:
    """A parsed, structurally-valid decision."""

    thought: str
    tool: str | None = None
    tool_input: dict[str, Any] = field(default_factory=dict)
    final_answer: str | None = None

    @property
    def is_final(self) -> bool:
        return self.final_answer is not None


def _strip_fences(text: str) -> str:
    """Remove a leading/trailing markdown code fence if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # Drop the opening fence line and any trailing fence.
        stripped = _FENCE_RE.sub("", stripped)
        # A trailing fence on its own line may remain; strip once more.
        stripped = re.sub(r"\s*```\s*$", "", stripped).strip()
    return stripped


def _extract_json_object(text: str) -> str:
    """Best-effort: isolate the outermost {...} so stray prose doesn't break us.

    We first try the whole (de-fenced) string; if that isn't a lone object we
    grab from the first '{' to the last '}'. json.loads still does the real
    validation — this only widens what we'll accept before giving up.
    """
    candidate = _strip_fences(text)
    if candidate.startswith("{") and candidate.endswith("}"):
        return candidate
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        return candidate[start : end + 1]
    return candidate


def parse(text: str, valid_tool_names: Iterable[str]) -> Decision:
    """Parse raw model text into a Decision.

    Raises MalformedDecision for structural problems (repair path) and
    UnknownTool when the (otherwise valid) decision names a missing tool.
    """
    # Step 1: narrow the raw text down to a JSON candidate, then really parse it.
    raw = _extract_json_object(text)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        # Repair path: the error message is fed back verbatim to the model, so it
        # spells out exactly what "valid" means.
        raise MalformedDecision(
            f"Response was not valid JSON ({e.msg}). Reply with exactly one "
            f"JSON object and nothing else — no prose, no markdown fences."
        ) from e

    # Step 2: must be a JSON object (not a list, number, string, ...).
    if not isinstance(obj, dict):
        raise MalformedDecision("Top-level JSON must be an object, not "
                                f"{type(obj).__name__}.")

    # `thought` is optional (defaults to "") but, if present, must be text.
    thought = obj.get("thought", "")
    if not isinstance(thought, str):
        raise MalformedDecision('"thought" must be a string.')

    # Step 3: exactly one of the two shapes must be present. Treat an explicit
    # null the same as absent so `{"tool": null, "final_answer": "..."}` works.
    has_tool = "tool" in obj and obj["tool"] is not None
    has_final = "final_answer" in obj and obj["final_answer"] is not None

    if has_tool and has_final:
        # Ambiguous: we can't both act and finish in one step.
        raise MalformedDecision(
            'Provide either "tool" or "final_answer", not both.'
        )
    if not has_tool and not has_final:
        # Neither branch chosen -> the decision is empty.
        raise MalformedDecision(
            'Object must contain either "tool" (to act) or "final_answer" '
            "(to finish)."
        )

    # Step 4a: final-answer branch — terminal, carries no tool.
    if has_final:
        final = obj["final_answer"]
        if not isinstance(final, str):
            raise MalformedDecision('"final_answer" must be a string.')
        return Decision(thought=thought, final_answer=final)

    # Step 4b: tool branch.
    tool = obj["tool"]
    if not isinstance(tool, str):
        raise MalformedDecision('"tool" must be a string.')

    # tool_input is optional; a missing or explicitly-null value means "no args".
    tool_input = obj.get("tool_input", {})
    if tool_input is None:
        tool_input = {}
    if not isinstance(tool_input, dict):
        raise MalformedDecision('"tool_input" must be a JSON object.')

    # Step 5: the decision is well-formed; only now check the tool exists. An
    # unknown name is NOT a structural error, so it gets its own exception type
    # and flows to the observation path (model self-corrects) rather than repair.
    valid = set(valid_tool_names)
    if tool not in valid:
        raise UnknownTool(tool, valid)

    return Decision(thought=thought, tool=tool, tool_input=tool_input)
