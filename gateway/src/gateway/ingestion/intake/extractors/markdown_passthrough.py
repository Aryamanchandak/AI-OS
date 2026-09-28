from __future__ import annotations

from pathlib import Path

from gateway.ingestion.intake.base import IntakeResult, text_sanity_issue


class MarkdownPassthroughExtractor:
    """Read a dropped UTF-8 Markdown file without rewriting its content."""

    def handles(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".md"

    def extract(self, path: Path) -> IntakeResult:
        markdown_text = path.read_text(encoding="utf-8")
        issue = text_sanity_issue(markdown_text)
        return IntakeResult(
            markdown_text=markdown_text,
            title=path.stem,
            needs_approval=issue is not None,
            approval_reason=issue,
            frontmatter={
                "source_filename": path.name,
                "extraction_method": "markdown_passthrough",
            },
        )


def extract_markdown(path: Path) -> IntakeResult:
    return MarkdownPassthroughExtractor().extract(path)
