"""
List directories inside the server sandbox.
"""
from __future__ import annotations

from sandbox import _safe
from tool_registry import register


@register(group="utility")
def list_dir(path: str = ".") -> dict:
    """List a directory inside the sandbox. Example: list_dir(".")."""
    p = _safe(path)
    if not p.exists():
        raise FileNotFoundError(f"Directory not found in sandbox: {path!r}")
    if not p.is_dir():
        raise ValueError(f"Path must be a directory in the sandbox: {path!r}")

    entries = []
    names: list[str] = []
    for child in sorted(p.iterdir()):
        is_dir = child.is_dir()
        entries.append({
            "name": child.name,
            "type": "dir" if is_dir else "file",
            "size_bytes": 0 if is_dir else child.stat().st_size,
        })
        names.append(child.name)
    return {"path": path, "count": len(entries), "names": names, "entries": entries}
