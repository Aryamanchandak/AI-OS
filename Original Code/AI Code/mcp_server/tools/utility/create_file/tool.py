"""
Create UTF-8 markdown files in the server sandbox.
"""
from __future__ import annotations

from sandbox import _safe_markdown_path
from tool_registry import register


@register(group="utility")
def create_file(path: str, content: str) -> dict:
    """Create a new markdown file in the sandbox; errors if it already exists. Example: create_file("hello.md", "hi")."""
    p = _safe_markdown_path(path)
    if p.exists():
        raise ValueError(f"File {path!r} already exists")
    if not p.parent.exists():
        raise FileNotFoundError(f"Parent directory of {path!r} does not exist")
    if not p.parent.is_dir():
        raise ValueError(f"Parent path of {path!r} is not a directory")

    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path, "size_bytes": p.stat().st_size, "encoding": "utf-8"}
