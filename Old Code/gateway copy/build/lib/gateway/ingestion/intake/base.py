from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol
import unicodedata

from pydantic import BaseModel, Field, model_validator


MIN_SANE_TEXT_LENGTH = 20
MAX_CONTROL_CHARACTER_RATIO = 0.02
SUSPICIOUS_UNICODE_CATEGORIES = {"Cc", "Cs", "Co"}


class IntakeResult(BaseModel):
    """Extractor output waiting to be published or approved."""

    markdown_text: str
    title: str = Field(min_length=1)
    needs_approval: bool
    approval_reason: str | None = None
    frontmatter: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def approval_has_a_reason(self) -> "IntakeResult":
        if self.needs_approval and not self.approval_reason:
            raise ValueError("approval_reason is required when needs_approval is true")
        if not self.needs_approval and self.approval_reason is not None:
            raise ValueError("approval_reason is only valid when approval is required")
        return self


class Extractor(Protocol):
    def handles(self, path: Path) -> bool: ...

    def extract(self, path: Path) -> IntakeResult: ...


def text_sanity_issue(text: str) -> str | None:
    """Return a cheap, deterministic reason that extracted text looks unsafe.

    This is deliberately conservative and does not pretend to validate meaning.
    OCR always requires approval independently of this check.
    """

    stripped = text.strip()
    if len(stripped) < MIN_SANE_TEXT_LENGTH:
        return f"extracted text is shorter than {MIN_SANE_TEXT_LENGTH} characters"

    suspicious_count = sum(
        1
        for character in text
        if character not in "\n\r\t"
        and unicodedata.category(character) in SUSPICIOUS_UNICODE_CATEGORIES
    )
    if suspicious_count / max(len(text), 1) > MAX_CONTROL_CHARACTER_RATIO:
        return "extracted text contains too many control or private-use characters"
    if "\ufffd" in text:
        return "extracted text contains Unicode replacement characters"
    return None
