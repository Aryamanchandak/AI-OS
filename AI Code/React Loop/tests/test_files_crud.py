"""The local-file CRUD tools write to an isolated store and enforce their guards.

Each test points CRUD_FILES_DIR at a fresh tmp dir (the tools re-read that env on
every call), so nothing touches the real Database/files store.
"""

import json

import pytest

from simple_server.tools.files import (
    file_create,
    file_delete,
    file_list,
    file_read,
    file_update,
    file_write_json,
)


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    return tmp_path


def test_create_read_roundtrip():
    assert "CREATED" in file_create("a.txt", "hello")
    assert file_read("a.txt") == "hello"


def test_create_rejects_duplicate():
    file_create("a.txt", "x")
    assert "already exists" in file_create("a.txt", "y")


def test_read_missing_file_is_an_error_not_a_crash():
    assert "does not exist" in file_read("nope.txt")


def test_update_overwrite_then_append():
    file_create("a.txt", "one")
    file_update("a.txt", "two", mode="overwrite")
    assert file_read("a.txt") == "two"
    file_update("a.txt", "-three", mode="append")
    assert file_read("a.txt") == "two-three"


def test_update_requires_existing_file():
    assert "does not exist" in file_update("missing.txt", "x")


def test_update_rejects_bad_mode():
    file_create("a.txt", "x")
    assert "mode must be" in file_update("a.txt", "y", mode="sideways")


def test_delete_removes_file():
    file_create("a.txt", "x")
    assert "DELETED" in file_delete("a.txt")
    assert "does not exist" in file_read("a.txt")


def test_list_reports_names_and_sizes():
    file_create("a.txt", "12345")
    file_create("b.md", "x")
    entries = {e["name"]: e["size_bytes"] for e in json.loads(file_list())}
    assert entries["a.txt"] == 5
    assert "b.md" in entries


@pytest.mark.parametrize("bad", ["../escape.txt", "sub/dir.txt", "..\\win.txt", "", ".."])
def test_rejects_unsafe_names(bad):
    # A traversal / nested / empty name must never create a file.
    assert "ERROR" in file_create(bad, "x")


def test_create_accepts_valid_json_object(tmp_path):
    out = file_create("data.json", '{"ok": true}')

    assert "CREATED" in out
    assert "valid JSON" in out
    assert json.loads(file_read("data.json")) == {"ok": True}


def test_create_accepts_valid_json_array():
    out = file_create("data.json", '[{"id": 1}]')

    assert "CREATED" in out
    assert json.loads(file_read("data.json")) == [{"id": 1}]


@pytest.mark.parametrize(
    "content",
    [
        "{'python': True}",
        "[item for item in range(3)]",
        '{"a": 1,}',
        '{"a":',
        "",
    ],
)
def test_create_rejects_invalid_json_without_writing(content, tmp_path):
    out = file_create("bad.json", content)

    assert out.startswith("ERROR: Invalid JSON")
    assert not (tmp_path / "bad.json").exists()


def test_invalid_json_update_does_not_corrupt_existing_file():
    file_create("data.json", '{"ok": true}')

    out = file_update("data.json", "{'ok': False}", mode="overwrite")

    assert out.startswith("ERROR: Invalid JSON")
    assert file_read("data.json") == '{"ok": true}'


def test_invalid_json_append_does_not_corrupt_existing_file():
    file_create("data.json", '{"ok": true}')

    out = file_update("data.json", "\n{}", mode="append")

    assert out.startswith("ERROR: Invalid JSON")
    assert file_read("data.json") == '{"ok": true}'


def test_file_write_json_serializes_structured_data():
    out = file_write_json(
        "customers.json",
        [{"customer_id": "C001", "balance": 1200}],
    )

    assert "CREATED" in out
    assert "valid JSON" in out
    assert json.loads(file_read("customers.json")) == [
        {"customer_id": "C001", "balance": 1200}
    ]


def test_file_write_json_requires_json_extension():
    out = file_write_json("customers.txt", [{"id": 1}])

    assert out.startswith("ERROR:")
    assert "only writes filenames ending in .json" in out


def test_file_write_json_does_not_overwrite_unless_requested():
    file_write_json("customers.json", [{"id": 1}])

    blocked = file_write_json("customers.json", [{"id": 2}])
    overwritten = file_write_json("customers.json", [{"id": 2}], overwrite=True)

    assert "already exists" in blocked
    assert "UPDATED" in overwritten
    assert json.loads(file_read("customers.json")) == [{"id": 2}]
