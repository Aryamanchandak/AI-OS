from __future__ import annotations

from pathlib import Path
from typing import Any

from ingestion.models import CaptureOutcome, CaptureRequest
from ingestion.pipeline import UnifiedIngestionPipeline


def capture_markdown_tree(
    pipeline: UnifiedIngestionPipeline,
    root: Path,
    *,
    source_type: str = "note",
    metadata: dict[str, Any] | None = None,
) -> list[CaptureOutcome]:
    """Read-only, deterministic Markdown-folder scanner.

    Adapter for any Markdown folder that is not being treated as an Obsidian
    vault (see sources/obsidian.py for that case).
    """
    resolved_root = root.expanduser().resolve()
    if not resolved_root.is_dir():
        raise NotADirectoryError(f"Markdown source root not found: {resolved_root}")
    outcomes: list[CaptureOutcome] = []
    for path in sorted(resolved_root.rglob("*.md")):
        if not path.is_file():
            continue
        outcomes.append(
            pipeline.capture(
                CaptureRequest(
                    source_type=source_type,
                    origin=str(path.resolve()),
                    content=path.read_bytes(),
                    metadata={
                        **(metadata or {}),
                        "source_relative_path": str(path.relative_to(resolved_root)),
                    },
                )
            )
        )
    return outcomes
