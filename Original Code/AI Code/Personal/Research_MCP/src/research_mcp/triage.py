"""Two-axis triage via Sonnet (§1.1 of the spec).

Returns {correctness, effort, confidence} per item. Confidence-driven escalation:
if confidence < 0.7 and effort == "light" → escalate to "deep".
"""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import TriageResult
from .meter import MeteredClient

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "triage.md"
_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0.2
_CONFIDENCE_ESCALATION_THRESHOLD = 0.7


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _parse_triage(raw: str) -> TriageResult:
    """Extract JSON from model output and validate into TriageResult."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    data = json.loads(text)
    result = TriageResult(**data)
    # Confidence-driven escalation
    if result.confidence < _CONFIDENCE_ESCALATION_THRESHOLD and result.effort == "light":
        result = result.model_copy(update={"effort": "deep"})
    return result


async def triage_item(item: str, meter: MeteredClient, run_id: str) -> TriageResult:
    system_prompt = _load_prompt()
    message = await meter.messages_create(
        model=_MODEL,
        stage="triage",
        run_id=run_id,
        max_tokens=256,
        temperature=_TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": item}],
    )
    raw = message.content[0].text
    return _parse_triage(raw)


async def split_claims(brief: str, meter: MeteredClient, run_id: str) -> list[str]:
    """Split a paragraph/brief into individual claim strings."""
    system = (
        "You are a claim extractor. Given a brief (paragraph or set of sentences), "
        "extract each distinct factual claim or topic as a separate item. "
        "Return a JSON array of strings, one per claim. No explanations."
    )
    message = await meter.messages_create(
        model=_MODEL,
        stage="claim_split",
        run_id=run_id,
        max_tokens=512,
        temperature=0.1,
        system=system,
        messages=[{"role": "user", "content": brief}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    return json.loads(raw)
