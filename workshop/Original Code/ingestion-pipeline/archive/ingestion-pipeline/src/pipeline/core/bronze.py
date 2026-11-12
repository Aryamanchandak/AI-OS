"""Shared helpers for reading bronze files.

Every consumer (KG, vector, sqlite) reads the raw bronze body the same way,
so the parsing lives here once. If two consumers stripped frontmatter
differently, their provenance lines would diverge (violates P1's intent that
all extractors see the identical bronze body).
"""

from __future__ import annotations

from pathlib import Path


def strip_frontmatter(raw: str) -> str:
    """Remove a leading YAML frontmatter block (``---\\n...\\n---``) from bronze text.

    Returns the body verbatim (minus the frontmatter). If there is no
    frontmatter block, returns the text unchanged.
    """
    if not raw.startswith("---"):
        return raw
    end = raw.find("\n---", 3)
    if end == -1:
        return raw
    return raw[end + 4 :].lstrip("\n")


def read_body(bronze_path: Path) -> str:
    """Read a bronze file and return its body (frontmatter stripped)."""
    return strip_frontmatter(bronze_path.read_text(encoding="utf-8"))
