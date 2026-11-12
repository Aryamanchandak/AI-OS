"""Shared local file-store core.

The single implementation behind BOTH the CRUD MCP tools
(``simple_server/tools/files.py``) and the podcast pipeline's artifact
persistence (``podcast_tools/storage.py``). Keeping it here — a dependency-free
top-level leaf that imports nothing from either package — means the podcast
library stays decoupled from the assignment server, and every file write in the
project flows through one traversal-safe implementation.

One flat store, rooted at ``podcast_tools/data`` by default and overridable with
``CRUD_FILES_DIR``. Names are sanitised to a single flat filename — no
directories, no ``..`` traversal — so nothing can write outside the store.

(The top-level ``Database/`` folder is the eventual target but is deferred for
now; point ``CRUD_FILES_DIR`` there when ready.)
"""

from __future__ import annotations

import os
from pathlib import Path

# React Loop/podcast_tools/data  (this file lives at React Loop/filestore.py)
_DEFAULT_DIR = Path(__file__).resolve().parent / "podcast_tools" / "data"


def base_dir() -> Path:
    """Resolve (and create) the store directory. Read fresh so CRUD_FILES_DIR can vary."""
    root = Path(os.environ.get("CRUD_FILES_DIR", str(_DEFAULT_DIR))).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def resolve(name: str) -> Path:
    """Turn a caller-supplied name into a safe path *inside* the store.

    Rejects anything that isn't a single flat filename: empty names, names with
    a path separator, and names that would escape the store via ``..``.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("file name must not be empty")
    if name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
        raise ValueError(f"invalid file name: {name!r} (must be a single filename)")

    base = base_dir()
    target = (base / name).resolve()
    if base not in target.parents and target != base:
        raise ValueError(f"resolved path escapes the store: {name!r}")
    return target


def write(name: str, content: str) -> Path:
    """Write ``content`` to ``name`` in the store (creating/overwriting). Returns the path."""
    path = resolve(name)
    path.write_text(content, encoding="utf-8")
    return path


def append(name: str, content: str) -> Path:
    """Append ``content`` to ``name`` in the store (creating it if absent). Returns the path."""
    path = resolve(name)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(content)
    return path


def read(name: str) -> str:
    """Read ``name`` from the store. Raises FileNotFoundError if it does not exist."""
    path = resolve(name)
    if not path.exists():
        raise FileNotFoundError(f"file not found in store: {name!r}")
    return path.read_text(encoding="utf-8")


def exists(name: str) -> bool:
    """Whether ``name`` exists in the store."""
    return resolve(name).exists()


def delete(name: str) -> bool:
    """Delete ``name`` from the store. Returns True if a file was removed."""
    path = resolve(name)
    if path.exists():
        path.unlink()
        return True
    return False


def list_files() -> list[Path]:
    """Every file in the store, sorted by name (directories excluded)."""
    return sorted(p for p in base_dir().iterdir() if p.is_file())
