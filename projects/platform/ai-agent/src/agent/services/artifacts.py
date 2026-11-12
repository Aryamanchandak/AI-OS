"""Content-addressable artifact store.

Raw bytes the agent fetches or produces live here, keyed by sha256 of the
content. Memory holds the handle + a short descriptor; this module owns the
bytes. Perception sees handles, Decision sees bytes only when Perception
attaches them. The 50 KB of HTML touches exactly one LLM call across a run.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading

from agent import STATE_DIR
from agent.schemas import Artifact

STORE = STATE_DIR / "artifacts"
STORE.mkdir(parents=True, exist_ok=True)
_LOCK_PATH = STORE / ".lock"
_thread_lock = threading.Lock()


def _digest_from_id(artifact_id: str) -> str:
    return artifact_id.removeprefix("art:")


def _atomic_write_bytes(path, blob: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(blob)
    tmp.replace(path)


def _atomic_write_text(path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text)
    tmp.replace(path)


def put(blob: bytes, *, content_type: str, source: str, descriptor: str) -> str:
    """Write blob (deduped by content hash) and return its handle."""
    digest = hashlib.sha256(blob).hexdigest()
    art_id = f"art:{digest}"
    bin_path = STORE / f"{digest}.bin"
    meta_path = STORE / f"{digest}.json"
    with _thread_lock:
        with open(_LOCK_PATH, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            if not bin_path.exists():
                _atomic_write_bytes(bin_path, blob)
            if not meta_path.exists():
                meta = Artifact(
                    id=art_id,
                    content_type=content_type,
                    size_bytes=len(blob),
                    source=source,
                    descriptor=descriptor,
                )
                _atomic_write_text(meta_path, meta.model_dump_json(indent=2))
            fcntl.flock(lf, fcntl.LOCK_UN)
    return art_id


def get_bytes(artifact_id: str) -> bytes:
    digest = _digest_from_id(artifact_id)
    return (STORE / f"{digest}.bin").read_bytes()


def get_meta(artifact_id: str) -> Artifact:
    digest = _digest_from_id(artifact_id)
    raw = json.loads((STORE / f"{digest}.json").read_text())
    return Artifact.model_validate(raw)


def exists(artifact_id: str) -> bool:
    digest = _digest_from_id(artifact_id)
    return (STORE / f"{digest}.bin").exists()


def list_ids() -> list[str]:
    """Return every artifact handle currently present in the byte store."""
    return sorted(f"art:{p.stem}" for p in STORE.glob("*.bin"))


def list_artifacts() -> list[Artifact]:
    """Return parsed metadata for artifacts with readable sidecars."""
    out: list[Artifact] = []
    for art_id in list_ids():
        try:
            out.append(get_meta(art_id))
        except FileNotFoundError:
            continue
    return out


def delete(artifact_id: str) -> None:
    """Delete one artifact's bytes and metadata if present."""
    digest = _digest_from_id(artifact_id)
    with _thread_lock:
        with open(_LOCK_PATH, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            for path in (STORE / f"{digest}.bin", STORE / f"{digest}.json"):
                if path.exists():
                    path.unlink()
            fcntl.flock(lf, fcntl.LOCK_UN)


def clear() -> None:
    """Delete all artifacts and sidecar metadata."""
    with _thread_lock:
        with open(_LOCK_PATH, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            for path in list(STORE.glob("*.bin")) + list(STORE.glob("*.json")):
                path.unlink()
            fcntl.flock(lf, fcntl.LOCK_UN)


def gc(referenced_ids: set[str], *, dry_run: bool = True) -> list[str]:
    """Delete artifacts not present in `referenced_ids`.

    Dry-run by default because a missed reference means data loss. Callers
    should inspect the returned ids before running with `dry_run=False`.
    """
    unreferenced = [art_id for art_id in list_ids() if art_id not in referenced_ids]
    if not dry_run:
        for art_id in unreferenced:
            delete(art_id)
    return unreferenced
