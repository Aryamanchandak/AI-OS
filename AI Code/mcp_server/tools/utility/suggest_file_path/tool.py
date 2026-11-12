"""
Suggest unused markdown file paths inside the server sandbox.
"""
from __future__ import annotations

import re

from sandbox import MARKDOWN_SUFFIXES, SANDBOX, _safe
from tool_registry import register


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "untitled"


def _markdown_extension(extension: str) -> str:
    ext = extension.strip().lower()
    if not ext:
        ext = "md"
    if not ext.startswith("."):
        ext = f".{ext}"
    if ext not in MARKDOWN_SUFFIXES:
        raise ValueError("extension must be .md or .markdown")
    return ext


@register(group="utility")
def suggest_file_path(purpose: str, directory: str = ".", extension: str = "md") -> dict:
    """Suggest an unused markdown file path in an existing sandbox directory. Example: suggest_file_path("RBI notes", "research")."""
    clean_purpose = purpose.strip()
    if not clean_purpose:
        raise ValueError("purpose cannot be empty.")

    clean_directory = directory.strip() or "."
    directory_path = _safe(clean_directory)
    if not directory_path.exists():
        raise FileNotFoundError(f"Directory not found in sandbox: {directory!r}")
    if not directory_path.is_dir():
        raise ValueError(f"Path must be a directory in the sandbox: {directory!r}")

    ext = _markdown_extension(extension)
    stem = _slugify(clean_purpose)
    filename = f"{stem}{ext}"
    candidate = directory_path / filename
    suffix = 2
    while candidate.exists():
        filename = f"{stem}-{suffix}{ext}"
        candidate = directory_path / filename
        suffix += 1

    suggested_path = candidate.relative_to(SANDBOX.resolve()).as_posix()
    suggested_directory = directory_path.relative_to(SANDBOX.resolve()).as_posix()

    return {
        "path": suggested_path,
        "directory": suggested_directory,
        "filename": filename,
        "exists": False,
        "reason": "first unused markdown filename for this purpose",
    }
