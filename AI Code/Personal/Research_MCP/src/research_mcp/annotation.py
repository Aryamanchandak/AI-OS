"""Sonnet annotation: one call per LogicalSource after dedup."""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import Annotation, LogicalSource
from .meter import MeteredClient

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "annotation.md"
_MODEL = "claude-sonnet-4-6"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _parse_annotation(raw: str, logical_source_id: str) -> Annotation:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    data = json.loads(text)
    return Annotation(
        logical_source_id=logical_source_id,
        relevance=float(data.get("relevance", 0.5)),
        key_findings=data.get("key_findings", []),
        credibility_tier=data.get("credibility_tier", "open_web"),
    )


async def annotate_sources(
    topic: str,
    sources: list[LogicalSource],
    meter: MeteredClient,
    run_id: str,
) -> list[Annotation]:
    """Annotate each LogicalSource with one Sonnet call."""
    system_prompt = _load_prompt()
    annotations: list[Annotation] = []

    for src in sources:
        user_content = json.dumps({
            "topic": topic,
            "source": {
                "title": src.title,
                "authors": src.authors,
                "published": src.published,
                "excerpt": src.raw_excerpt,
                "credibility_context": src.provenance[0].source_tier if src.provenance else "unknown",
            },
        })
        message = await meter.messages_create(
            model=_MODEL,
            stage="annotation",
            run_id=run_id,
            max_tokens=512,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        annotations.append(_parse_annotation(message.content[0].text, src.id))

    return annotations
