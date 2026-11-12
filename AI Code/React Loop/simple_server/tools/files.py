"""Local-file CRUD tools — the assignment's "CRUD on a local file" function.

Five explicit operations (create / read / update / delete / list) over the shared
file store (``filestore``), the same store the podcast pipeline writes its
artifacts to. Everything is rooted at a single directory
(``podcast_tools/data/`` by default, or ``$CRUD_FILES_DIR``) and every name is
sanitised to a single flat filename, so the agent can never write outside it.

These are the agent-facing wrappers: they add the create-vs-update semantics and
return human-readable status strings. The actual read/write lives in
``filestore`` so there is exactly one implementation of "touch a file in the
store" in the project.
"""

from __future__ import annotations

import json
from typing import Any

import filestore

from ..app import mcp


def _is_json_name(name: str) -> bool:
    return name.strip().lower().endswith(".json")


def _json_error(exc: json.JSONDecodeError) -> str:
    return (
        f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}. "
        "The file was not written."
    )


def _validate_json_content(name: str, content: str) -> str | None:
    if not _is_json_name(name):
        return None
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        return _json_error(exc)
    return None


@mcp.tool()
def file_create(name: str, content: str = "") -> str:
    """Create a NEW file in the local store and write ``content`` to it.

    Fails if a file with that name already exists (use ``file_update`` to change
    an existing file). ``name`` is a single filename such as "tata_sons.txt" or
    "notes.md" — no folders. Returns the saved path.
    """
    try:
        if filestore.exists(name):
            return f"ERROR: '{name}' already exists — use file_update to modify it."
        validation_error = _validate_json_content(name, content)
        if validation_error:
            return f"ERROR: {validation_error}"
        path = filestore.write(name, content)
    except ValueError as e:  # noqa: BLE001 -- surface a clean error to the agent
        return f"ERROR: {e}"
    suffix = " valid JSON" if _is_json_name(name) else ""
    return f"CREATED {path} ({len(content)} chars){suffix}"


@mcp.tool()
def file_write_json(path: str, data: Any, overwrite: bool = False) -> str:
    """Create or overwrite a JSON file from structured data.

    Use this for ``.json`` output instead of hand-serializing JSON text. The
    ``path`` must be a single filename ending in ``.json``. ``data`` may be any
    JSON-serializable object. Set ``overwrite=true`` to replace an existing file.
    """
    if not _is_json_name(path):
        return "ERROR: file_write_json only writes filenames ending in .json."
    try:
        if filestore.exists(path) and not overwrite:
            return f"ERROR: '{path}' already exists — set overwrite=true to replace it."
        content = json.dumps(data, ensure_ascii=False, indent=2)
        # Round-trip once so future encoder changes cannot bypass validation.
        json.loads(content)
        saved = filestore.write(path, content)
    except TypeError as e:
        return f"ERROR: data is not JSON-serializable: {e}. The file was not written."
    except ValueError as e:
        return f"ERROR: {e}"
    action = "UPDATED" if overwrite else "CREATED"
    return f"{action} {saved} ({saved.stat().st_size} bytes, valid JSON)"


@mcp.tool()
def file_read(name: str) -> str:
    """Read and return the full text content of a file from the local store."""
    try:
        return filestore.read(name)
    except ValueError as e:  # noqa: BLE001
        return f"ERROR: {e}"
    except FileNotFoundError:
        return f"ERROR: '{name}' does not exist."


@mcp.tool()
def file_update(name: str, content: str, mode: str = "overwrite") -> str:
    """Update an EXISTING file in the local store.

    ``mode`` is either "overwrite" (replace the whole file, the default) or
    "append" (add ``content`` to the end). Fails if the file does not exist —
    use ``file_create`` for a new file. Returns the saved path and new size.
    """
    if mode not in ("overwrite", "append"):
        return f"ERROR: mode must be 'overwrite' or 'append', got {mode!r}."
    try:
        if not filestore.exists(name):
            return f"ERROR: '{name}' does not exist — use file_create first."
        new_content = filestore.read(name) + content if mode == "append" else content
        validation_error = _validate_json_content(name, new_content)
        if validation_error:
            return f"ERROR: {validation_error}"
        path = filestore.write(name, new_content)
    except ValueError as e:  # noqa: BLE001
        return f"ERROR: {e}"
    suffix = ", valid JSON" if _is_json_name(name) else ""
    return f"UPDATED {path} (mode={mode}, now {path.stat().st_size} bytes{suffix})"


@mcp.tool()
def file_delete(name: str) -> str:
    """Delete a file from the local store. Returns whether it was removed."""
    try:
        removed = filestore.delete(name)
    except ValueError as e:  # noqa: BLE001
        return f"ERROR: {e}"
    if not removed:
        return f"ERROR: '{name}' does not exist."
    return f"DELETED {filestore.resolve(name)}"


@mcp.tool()
def file_list() -> str:
    """List every file in the local store as JSON: [{name, size_bytes}, ...]."""
    entries = [
        {"name": p.name, "size_bytes": p.stat().st_size}
        for p in filestore.list_files()
    ]
    return json.dumps(entries, indent=2)
