"""Dual-mode Opus synthesis: exposition or refutation, single call (§2, §3).

Selects prompt template by triage.correctness:
  "false"  → synthesis_refutation.md
  else     → synthesis_exposition.md

Sources injected with stable S1, S2... labels. Output must tag every factual
sentence with [Sn]. The citation gate (citation_gate.py) verifies this deterministically.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .contracts import Annotation, LogicalSource, TriageResult
from .meter import MeteredClient

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_MODEL_DEEP = "claude-opus-4-7"
_MODEL_LIGHT = "claude-sonnet-4-6"


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text()


def _build_source_block(sources: list[LogicalSource], annotations: list[Annotation]) -> str:
    ann_by_id = {a.logical_source_id: a for a in annotations}
    lines: list[str] = []
    for i, src in enumerate(sources, start=1):
        label = f"S{i}"
        ann = ann_by_id.get(src.id)
        findings = "; ".join(ann.key_findings[:3]) if ann else ""
        lines.append(
            f"[{label}] {src.title}"
            + (f" ({src.published})" if src.published else "")
            + (f" — {src.url}" if src.url else "")
            + f"\nExcerpt: {src.raw_excerpt[:800]}"
            + (f"\nKey findings: {findings}" if findings else "")
        )
    return "\n\n".join(lines)


async def synthesize(
    topic: str,
    triage: TriageResult,
    sources: list[LogicalSource],
    annotations: list[Annotation],
    meter: MeteredClient,
    run_id: str,
    run_dir: Path,
    *,
    model: str = _MODEL_DEEP,
    stage: str = "synthesis",
) -> str:
    """Generate and persist the synthesis essay. Returns the essay text."""
    prompt_file = "synthesis_refutation.md" if triage.correctness == "false" else "synthesis_exposition.md"
    system_prompt = _load_prompt(prompt_file)
    source_block = _build_source_block(sources, annotations)

    user_content = json.dumps({
        "topic": topic,
        "triage": triage.model_dump(),
        "sources": source_block,
    })

    message = await meter.messages_create(
        model=model,
        stage=stage,
        run_id=run_id,
        max_tokens=4096,
        temperature=0.3,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    essay = message.content[0].text

    # Atomic write: temp file + os.rename (idempotent)
    run_dir.mkdir(parents=True, exist_ok=True)
    essay_path = run_dir / "essay.md"
    tmp_fd, tmp_path = tempfile.mkstemp(dir=run_dir, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as fh:
            fh.write(essay)
        os.rename(tmp_path, essay_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return essay
