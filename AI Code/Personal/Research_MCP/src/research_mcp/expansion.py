"""Opus expansion stage: decomposes a topic/claim into faceted proxy search queries (§3).

Called only for effort == "deep".
For correctness=="false": refutation-flavored decomposition.
For topic / true+rich: exposition decomposition.
"""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import TriageResult
from .meter import MeteredClient

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "expansion.md"
_MODEL = "claude-opus-4-7"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _parse_queries(raw: str) -> list[str]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    data = json.loads(text)
    if isinstance(data, list):
        return [str(q) for q in data]
    # Handle {"queries": [...]} shape
    return [str(q) for q in data.get("queries", [])]


async def expand_topic(item: str, triage: TriageResult, meter: MeteredClient, run_id: str) -> list[str]:
    """Return a list of proxy search strings for the given item."""
    system_prompt = _load_prompt()
    mode = "refutation" if triage.correctness == "false" else "exposition"
    user_content = json.dumps({"item": item, "mode": mode, "rationale": triage.rationale})

    message = await meter.messages_create(
        model=_MODEL,
        stage="expansion",
        run_id=run_id,
        max_tokens=1024,
        temperature=0.3,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = message.content[0].text
    return _parse_queries(raw)
