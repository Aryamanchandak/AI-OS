"""Create, read, update and delete notes in one local JSON file.

A note is something you read and may want to rely on later: a title, the
text, where it came from, and whether you have verified it yet.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Status = Literal["unverified", "verified"]


class Note(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    title: str
    body: str
    source_url: str = ""
    status: Status = "unverified"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


class NoteNotFound(KeyError):
    pass


def notes_path() -> Path:
    """`A04_NOTES_FILE` if set, else `data/notes.json` beside this file."""
    default = Path(__file__).resolve().parent / "data" / "notes.json"
    return Path(os.getenv("A04_NOTES_FILE", default))


def list_notes() -> list[Note]:
    path = notes_path()
    if not path.exists():
        return []
    return [Note.model_validate(n) for n in json.loads(path.read_text())]


def _save(notes: list[Note]) -> None:
    path = notes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps([n.model_dump() for n in notes], indent=2))
    tmp.replace(path)  # atomic: a crash never leaves a half-written file


def create_note(title: str, body: str, source_url: str = "") -> Note:
    if not title.strip():
        raise ValueError("A note needs a title.")
    note = Note(title=title.strip(), body=body, source_url=source_url)
    _save([*list_notes(), note])
    return note


def get_note(note_id: str) -> Note:
    for note in list_notes():
        if note.id == note_id:
            return note
    raise NoteNotFound(note_id)


def update_note(
    note_id: str,
    *,
    title: str | None = None,
    body: str | None = None,
    source_url: str | None = None,
    status: Status | None = None,
) -> Note:
    notes = list_notes()
    for i, note in enumerate(notes):
        if note.id == note_id:
            changes = {
                k: v
                for k, v in {
                    "title": title, "body": body, "source_url": source_url, "status": status,
                }.items()
                if v is not None
            }
            notes[i] = Note.model_validate({**note.model_dump(), **changes})
            _save(notes)
            return notes[i]
    raise NoteNotFound(note_id)


def delete_note(note_id: str) -> None:
    notes = list_notes()
    kept = [n for n in notes if n.id != note_id]
    if len(kept) == len(notes):
        raise NoteNotFound(note_id)
    _save(kept)


def counts() -> dict[str, int]:
    notes = list_notes()
    verified = sum(1 for n in notes if n.status == "verified")
    return {"total": len(notes), "verified": verified, "unverified": len(notes) - verified}
