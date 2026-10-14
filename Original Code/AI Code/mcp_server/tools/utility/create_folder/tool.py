"""
Create folders inside the server sandbox.
"""
from __future__ import annotations

from sandbox import _safe
from tool_registry import register


@register(group="utility")
def create_folder(path: str, create_parents: bool = False) -> dict:
    """Create a folder inside the sandbox. Example: create_folder("reports/2026", create_parents=True)."""
    clean_path = path.strip()
    if not clean_path:
        raise ValueError("path cannot be empty.")

    p = _safe(clean_path)
    if p.exists():
        raise ValueError(f"Folder {path!r} already exists")

    if create_parents:
        p.mkdir(parents=True, exist_ok=False)
    else:
        if not p.parent.exists():
            raise FileNotFoundError(f"Parent directory of {path!r} does not exist")
        if not p.parent.is_dir():
            raise ValueError(f"Parent path of {path!r} is not a directory")
        p.mkdir()

    return {"ok": True, "path": clean_path}
