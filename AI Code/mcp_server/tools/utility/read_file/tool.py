"""
Read UTF-8 markdown files from the server sandbox.
"""
from __future__ import annotations

from sandbox import _safe_markdown_path
from tool_registry import register


@register(group="utility")
def read_file(path: str) -> dict:
    """Read a UTF-8 markdown file from the sandbox. Example: read_file("notes.md")."""
    p = _safe_markdown_path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found in sandbox: {path!r}")
    if not p.is_file():
        raise ValueError(f"Path must be a markdown file in the sandbox: {path!r}")

    text = p.read_text(encoding="utf-8")
    return {
        "path": path,
        "size_bytes": p.stat().st_size,
        "content": text,
        "encoding": "utf-8",
    }
