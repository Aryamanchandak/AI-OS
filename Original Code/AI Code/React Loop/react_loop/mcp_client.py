"""Component 3.2 — MCP client (spine).

Thin wrapper over the MCP Python SDK's stdio client. Gives the loop exactly two
verbs plus discovery:

    await client.list_tools()          -> list[ToolSpec]   (name/description/schema)
    await client.call_tool(name, args) -> str              (normalized to text)

MCP replaces the hand-built tool registry: it hands us the registry, the JSON
schemas, and invocation for free. This module is server-agnostic — it never
names a tool; it only relays whatever the connected server exposes.

Lifecycle note (deliberate): the SDK's session is an async context manager that
must stay open for *every* call in a run. So this client is itself an async
context manager — open it once, keep it open for the whole loop, close on exit.
"""

from __future__ import annotations

import logging
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import ServerConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    """What the renderer and parser need to know about one tool."""

    name: str
    description: str
    input_schema: dict[str, Any]


def _normalize_content(content: list[Any]) -> str:
    """MCP returns a list of content blocks, not a string. Flatten to text.

    Text blocks contribute their text; anything else contributes a readable
    placeholder so the observation is never silently empty.
    """
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
        else:
            btype = getattr(block, "type", type(block).__name__)
            parts.append(f"[{btype} content omitted]")
    return "\n".join(parts).strip()


class MCPClient:
    """Async stdio MCP client, scoped to one server for one run."""

    def __init__(self, server: ServerConfig) -> None:
        self._server = server
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> "MCPClient":
        self._stack = AsyncExitStack()
        env = os.environ.copy()
        if self._server.env:
            env.update(self._server.env)
        params = StdioServerParameters(
            command=self._server.command,
            args=self._server.args,
            cwd=self._server.cwd,
            env=env,
        )
        logger.info(
            "launching MCP server: %s %s",
            self._server.command, " ".join(self._server.args),
        )
        try:
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except BaseException:
            # Startup failed (e.g. the server crashed on import). Tear the
            # partially-entered stack down *in this task* so we don't leak an
            # anyio cancel scope, then re-raise the real error.
            await self._stack.aclose()
            self._stack = None
            raise
        self._session = session
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    @property
    def _live(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("MCPClient used outside its `async with` block")
        return self._session

    async def list_tools(self) -> list[ToolSpec]:
        result = await self._live.list_tools()
        specs = [
            ToolSpec(
                name=t.name,
                description=t.description or "",
                input_schema=t.inputSchema or {},
            )
            for t in result.tools
        ]
        logger.info("discovered %d tool(s): %s", len(specs), [s.name for s in specs])
        return specs

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool and return its output as text.

        A tool that *raises* on the server surfaces here as ``result.isError``
        with the error text in the content — we return that text rather than
        throwing, because README.md defines tool failure as normal control
        flow: it becomes an observation the model corrects from.
        """
        logger.debug("call_tool: %s args=%s", name, arguments or {})
        result = await self._live.call_tool(name, arguments or {})
        text = _normalize_content(list(result.content))
        if getattr(result, "isError", False):
            logger.warning("call_tool: %s reported an error", name)
            return f"ERROR: {text}" if text else "ERROR: tool reported failure"
        return text
