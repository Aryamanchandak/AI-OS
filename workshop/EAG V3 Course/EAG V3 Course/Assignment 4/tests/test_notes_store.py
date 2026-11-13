"""The notes file: create, read, update, delete, and what happens on bad input."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

import notes_store as store


@pytest.fixture(autouse=True)
def notes_file(tmp_path, monkeypatch):
    path = tmp_path / "notes.json"
    monkeypatch.setenv("A04_NOTES_FILE", str(path))
    return path


def test_a_new_note_is_written_to_the_file_as_unverified(notes_file):
    note = store.create_note("Duration", "Bond prices fall when yields rise.", "https://example.com")
    on_disk = json.loads(notes_file.read_text())
    assert on_disk[0]["id"] == note.id
    assert on_disk[0]["status"] == "unverified"
    assert on_disk[0]["source_url"] == "https://example.com"


def test_no_file_yet_means_no_notes():
    assert store.list_notes() == []
    assert store.counts() == {"total": 0, "verified": 0, "unverified": 0}


def test_a_note_can_be_read_back_by_id():
    note = store.create_note("Duration", "text")
    assert store.get_note(note.id).title == "Duration"


def test_marking_a_note_verified_changes_only_its_status():
    note = store.create_note("Duration", "text")
    updated = store.update_note(note.id, status="verified")
    assert updated.status == "verified"
    assert updated.title == "Duration" and updated.body == "text"
    assert store.counts() == {"total": 1, "verified": 1, "unverified": 0}


def test_deleting_a_note_removes_only_that_note():
    keep = store.create_note("Keep", "a")
    drop = store.create_note("Drop", "b")
    store.delete_note(drop.id)
    assert [n.id for n in store.list_notes()] == [keep.id]


def test_a_note_without_a_title_is_refused():
    with pytest.raises(ValueError):
        store.create_note("   ", "text")
    assert store.list_notes() == []


def test_an_unknown_status_is_refused_and_the_file_is_untouched(notes_file):
    note = store.create_note("Duration", "text")
    before = notes_file.read_text()
    with pytest.raises(ValidationError):
        store.update_note(note.id, status="probably")
    assert notes_file.read_text() == before


@pytest.mark.parametrize("call", [
    lambda: store.get_note("nope"),
    lambda: store.update_note("nope", title="x"),
    lambda: store.delete_note("nope"),
])
def test_an_unknown_id_fails_loudly(call):
    with pytest.raises(store.NoteNotFound):
        call()
