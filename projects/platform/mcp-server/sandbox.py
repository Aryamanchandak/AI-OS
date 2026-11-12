"""
Shared sandbox for utility file tools.
All file paths from the model are resolved through _safe() before any I/O.
"""
from pathlib import Path

SANDBOX = Path(__file__).parent / "sandbox"
SANDBOX.mkdir(exist_ok=True)
MARKDOWN_SUFFIXES = {".md", ".markdown"}


def _safe(path: str) -> Path:
    """Resolve `path` inside the sandbox. Raises ValueError on traversal attempts."""
    p = (SANDBOX / path).resolve()
    base = SANDBOX.resolve()
    if p != base and base not in p.parents:
        raise ValueError(f"Path '{path}' escapes the sandbox")
    return p


def _safe_markdown_path(path: str) -> Path:
    """Resolve a markdown file path inside the sandbox."""
    p = _safe(path)
    if p.suffix.lower() not in MARKDOWN_SUFFIXES:
        raise ValueError("path must point to a markdown file ending in .md or .markdown")
    return p
