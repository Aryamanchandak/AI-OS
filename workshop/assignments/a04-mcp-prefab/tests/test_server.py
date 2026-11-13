"""The server as an MCP client sees it: three tools, and what each does."""

from __future__ import annotations

import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import server


@pytest.fixture(autouse=True)
def notes_file(tmp_path, monkeypatch):
    path = tmp_path / "notes.json"
    monkeypatch.setenv("A04_NOTES_FILE", str(path))
    return path


async def _call(name: str, args: dict):
    async with Client(server.mcp) as client:
        return await client.call_tool(name, args)


async def test_the_server_offers_exactly_the_three_tools():
    async with Client(server.mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == {"lookup_topic", "notes_file", "show_notebook"}


async def test_create_then_read_goes_through_the_file(notes_file):
    made = (await _call("notes_file", {"action": "create", "title": "Tata Sons", "body": "Holding company"})).data
    note_id = made["note"]["id"]
    assert json.loads(notes_file.read_text())[0]["id"] == note_id

    read = (await _call("notes_file", {"action": "read", "note_id": note_id})).data
    assert read["note"]["title"] == "Tata Sons"
    assert read["counts"] == {"total": 1, "verified": 0, "unverified": 1}


async def test_update_and_delete_keep_the_counts_right():
    made = (await _call("notes_file", {"action": "create", "title": "A", "body": "b"})).data
    note_id = made["note"]["id"]

    updated = (await _call("notes_file", {"action": "update", "note_id": note_id, "status": "verified"})).data
    assert updated["note"]["status"] == "verified"
    assert updated["chart"] == [
        {"status": "Verified", "notes": 1},
        {"status": "Unverified", "notes": 0},
    ]

    deleted = (await _call("notes_file", {"action": "delete", "note_id": note_id})).data
    assert deleted["notes"] == [] and deleted["counts"]["total"] == 0


async def test_a_bad_request_is_an_error_not_a_silent_success():
    with pytest.raises(ToolError):
        await _call("notes_file", {"action": "delete", "note_id": "nope"})
    with pytest.raises(ToolError):
        await _call("notes_file", {"action": "shred"})


async def test_the_dashboard_carries_the_saved_notes():
    await _call("notes_file", {"action": "create", "title": "Tata Sons", "body": "Holding company"})
    result = await _call("show_notebook", {"topic": "Tata"})
    payload = json.dumps(result.structured_content)
    assert "Tata Sons" in payload
    assert "Research notebook" in payload
    assert "notes_file" in payload  # the buttons call back into the file tool


@pytest.mark.network
async def test_lookup_finds_a_real_page():
    found = (await _call("lookup_topic", {"topic": "Claude Shannon"})).data
    assert found["found"] is True
    assert "Shannon" in found["title"]
    assert "wikipedia.org" in found["url"]
    assert len(found["summary"]) > 50
