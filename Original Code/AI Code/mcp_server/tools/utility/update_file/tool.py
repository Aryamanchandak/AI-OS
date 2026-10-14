"""
Overwrite UTF-8 markdown files in the server sandbox.
"""
from __future__ import annotations

from sandbox import _safe_markdown_path
from tool_registry import register


@register(group="utility")
def update_file(path: str, content: str) -> dict:
    """Overwrite an existing markdown file in the sandbox. Example: update_file("hello.md", "new body")."""
    p = _safe_markdown_path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found in sandbox: {path!r}")
    if not p.is_file():
        raise ValueError(f"Path must be a markdown file in the sandbox: {path!r}")

    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path, "size_bytes": p.stat().st_size, "encoding": "utf-8"}
