"""The bundled simple_server is reachable and its tools work end to end.

Launches it exactly as the loop does (python -m simple_server over stdio) and
checks discovery + a real tool call. Guards against a tool file breaking the
auto-import or the server failing to start.
"""

import os
import sys
from pathlib import Path

from react_loop.config import ServerConfig
from react_loop.mcp_client import MCPClient

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DATA = Path(_REPO) / "podcast_tools" / "data"


def _simple_server() -> ServerConfig:
    return ServerConfig(command=sys.executable, args=["-m", "simple_server"], cwd=_REPO)


async def test_discovers_starter_tools():
    async with MCPClient(_simple_server()) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"calculator", "get_current_time", "text_stats"} <= names


async def test_discovers_read_only_search_tools():
    async with MCPClient(_simple_server()) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"website_search", "research_search"} <= names


async def test_calculator_tool_runs():
    async with MCPClient(_simple_server()) as client:
        out = await client.call_tool("calculator", {"expression": "12.5/100 * 4800"})
    assert out.strip() == "600"


async def test_calculator_rejects_unsafe_input():
    async with MCPClient(_simple_server()) as client:
        out = await client.call_tool("calculator", {"expression": "__import__('os')"})
    assert "ERROR" in out


async def test_mcp_server_inherits_crud_files_dir(monkeypatch, tmp_path):
    target = tmp_path / "store"
    default_file = _DEFAULT_DATA / "mcp_env_inheritance_check.txt"
    if default_file.exists():
        default_file.unlink()
    monkeypatch.setenv("CRUD_FILES_DIR", str(target))

    async with MCPClient(_simple_server()) as client:
        created = await client.call_tool(
            "file_create",
            {"name": "mcp_env_inheritance_check.txt", "content": "ok"},
        )
        listed = await client.call_tool("file_list", {})
        read = await client.call_tool(
            "file_read",
            {"name": "mcp_env_inheritance_check.txt"},
        )

    assert "CREATED" in created
    assert (target / "mcp_env_inheritance_check.txt").read_text() == "ok"
    assert "mcp_env_inheritance_check.txt" in listed
    assert read == "ok"
    assert not default_file.exists()


async def test_mcp_server_explicit_env_overrides_parent(monkeypatch, tmp_path):
    inherited = tmp_path / "inherited"
    override = tmp_path / "override"
    monkeypatch.setenv("CRUD_FILES_DIR", str(inherited))
    server = ServerConfig(
        command=sys.executable,
        args=["-m", "simple_server"],
        cwd=_REPO,
        env={"CRUD_FILES_DIR": str(override)},
    )

    async with MCPClient(server) as client:
        out = await client.call_tool(
            "file_create",
            {"name": "mcp_env_override_check.txt", "content": "ok"},
        )

    assert "CREATED" in out
    assert not (inherited / "mcp_env_override_check.txt").exists()
    assert (override / "mcp_env_override_check.txt").read_text() == "ok"
