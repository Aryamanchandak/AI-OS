"""
Append UTF-8 markdown content to existing sandbox files.
"""
from __future__ import annotations

from sandbox import _safe_markdown_path
from tool_registry import register


@register(group="utility")
def append_file(path: str, content: str, separator: str = "\n") -> dict:
    """Append text to an existing sandbox markdown file. Example: append_file("notes.md", "## Source 2\\nMore notes.")."""
    if content == "":
        raise ValueError("content cannot be empty.")

    p = _safe_markdown_path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found in sandbox: {path!r}")
    if not p.is_file():
        raise ValueError(f"Path must be a markdown file in the sandbox: {path!r}")

    prefix = separator if p.stat().st_size > 0 else ""
    appended_text = f"{prefix}{content}"
    with p.open("a", encoding="utf-8") as handle:
        handle.write(appended_text)

    return {
        "ok": True,
        "path": path,
        "bytes_appended": len(appended_text.encode("utf-8")),
        "size_bytes": p.stat().st_size,
        "encoding": "utf-8",
    }
