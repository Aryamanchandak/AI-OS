"""
Find-and-replace edits for UTF-8 markdown files in the server sandbox.
"""
from __future__ import annotations

from sandbox import _safe_markdown_path
from tool_registry import register


@register(group="utility")
def edit_file(path: str, find: str, replace: str, replace_all: bool = False) -> dict:
    """Find-and-replace inside a sandbox markdown file. Errors if find appears more than once and replace_all is False. Example: edit_file("hello.md", "foo", "bar")."""
    if find == "":
        raise ValueError("find cannot be empty.")

    p = _safe_markdown_path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found in sandbox: {path!r}")
    if not p.is_file():
        raise ValueError(f"Path must be a markdown file in the sandbox: {path!r}")

    text = p.read_text(encoding="utf-8")
    count = text.count(find)
    if count == 0:
        raise ValueError(f"{find!r} not found in {path!r}")
    if count > 1 and not replace_all:
        raise ValueError(
            f"{find!r} occurs {count} times in {path!r}; pass replace_all=True"
        )

    new_text = text.replace(find, replace) if replace_all else text.replace(find, replace, 1)
    p.write_text(new_text, encoding="utf-8")
    replacements = count if replace_all else 1
    return {
        "ok": True,
        "path": path,
        "replacements": replacements,
        "size_bytes": p.stat().st_size,
        "encoding": "utf-8",
    }
