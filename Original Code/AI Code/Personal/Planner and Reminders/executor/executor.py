# Version: V2
"""
Deterministic executor — processes confirmed queue items via the MCP server.

Flow:
  1. Read queue.md — filter status == "confirmed"
  2. For each confirmed item: validate with Pydantic, call MCP tool, update status
  3. MCP server is spawned as a short-lived subprocess (stdio transport, asyncio, no fork)

Self-trigger guard: if no confirmed items, return immediately.
This means the executor's own status writes (done/failed) never re-trigger processing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import TypeAdapter, ValidationError

# Allow imports from project root when run as a module
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import QueueItem
import queue_manager
import history_manager

logger = logging.getLogger(__name__)

_ITEM_ADAPTER: TypeAdapter[QueueItem] = TypeAdapter(QueueItem)

# Path to the MCP server module
_MCP_SERVER = str(Path(__file__).parent.parent / "mcp_server" / "applescript_mcp.py")
_PYTHON = sys.executable

_server_params = StdioServerParameters(
    command=_PYTHON,
    args=[_MCP_SERVER],
    env={
        **os.environ,
        "APPLE_CALENDAR_NAME": os.getenv("APPLE_CALENDAR_NAME", "Calendar"),
        "APPLE_REMINDER_LIST": os.getenv("APPLE_REMINDER_LIST", "Work Tracker"),
    },
)


# ── Item → MCP tool call mapping ──────────────────────────────────────────────

def _item_to_tool_call(item: QueueItem) -> tuple[str, dict[str, Any]]:
    """Return (tool_name, arguments) for the given confirmed queue item."""
    t = item.type

    if t == "create_event":
        return "create_event", {
            "title": item.title,
            "date": item.date.isoformat(),
            **({"time": item.time.strftime("%H:%M")} if item.time else {}),
            "duration_minutes": item.duration_minutes,
            "description": item.description,
        }

    if t == "create_reminder":
        return "create_reminder", {
            "title": item.title,
            "date": item.date.isoformat(),
            "time": item.time.strftime("%H:%M"),
            "description": item.description,
        }

    if t == "move_event":
        return "move_event", {
            "original_title": item.original_title,
            "original_date": item.original_date.isoformat(),
            "original_start": item.original_start.strftime("%H:%M"),
            "new_date": item.new_date.isoformat(),
            "new_start": item.new_start.strftime("%H:%M"),
            "duration_minutes": item.duration_minutes,
        }

    if t == "edit_event":
        args: dict[str, Any] = {
            "title": item.title,
            "date": item.date.isoformat(),
        }
        if item.new_title is not None:
            args["new_title"] = item.new_title
        if item.new_description is not None:
            args["new_description"] = item.new_description
        if item.new_duration_minutes is not None:
            args["new_duration_minutes"] = item.new_duration_minutes
        return "edit_event", args

    if t == "update_reminder_date":
        args = {
            "title": item.title,
            "list_name": item.list_name,
            "new_date": item.new_date.isoformat(),
        }
        if item.new_time is not None:
            args["new_time"] = item.new_time.strftime("%H:%M")
        return "update_reminder_date", args

    if t == "edit_reminder":
        args = {
            "title": item.title,
            "list_name": item.list_name,
        }
        if item.new_title is not None:
            args["new_title"] = item.new_title
        if item.new_description is not None:
            args["new_description"] = item.new_description
        return "edit_reminder", args

    if t == "delete_event":
        return "delete_event", {
            "title": item.title,
            "date": item.date.isoformat(),
        }

    if t == "delete_reminder":
        return "delete_reminder", {
            "title": item.title,
            "list_name": item.list_name,
        }

    raise ValueError(f"Unknown item type: {t}")


# ── Core execution ────────────────────────────────────────────────────────────

async def execute_confirmed() -> list[dict]:
    """
    Process all confirmed queue items.
    Returns a list of result dicts: {"id", "status", "result" | "error"}.
    """
    confirmed = queue_manager.list_by_status("confirmed")
    if not confirmed:
        return []

    results = []

    async with stdio_client(_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            for item in confirmed:
                try:
                    tool_name, tool_args = _item_to_tool_call(item)
                    response = await session.call_tool(tool_name, tool_args)

                    # Check if any content block signals an error
                    error_text = None
                    for content in response.content:
                        if hasattr(content, "text") and content.text.startswith("ERROR:"):
                            error_text = content.text[len("ERROR:"):].strip()
                            break

                    if error_text:
                        queue_manager.update_item_status(item.id, "failed", error=error_text)
                        results.append({"id": item.id, "status": "failed", "error": error_text})
                        logger.error("Item %s failed: %s", item.id, error_text)
                    else:
                        result_text = " ".join(
                            c.text for c in response.content if hasattr(c, "text")
                        )
                        queue_manager.update_item_status(item.id, "done")
                        try:
                            history_manager.record_action(item)
                        except Exception as exc:
                            logger.warning("history_manager failed for %s: %s", item.id, exc)
                        results.append({"id": item.id, "status": "done", "result": result_text})
                        logger.info("Item %s done: %s", item.id, result_text)

                except ValidationError as e:
                    msg = f"Pydantic validation error: {e}"
                    queue_manager.update_item_status(item.id, "failed", error=msg)
                    results.append({"id": item.id, "status": "failed", "error": msg})
                    logger.error("Item %s validation failed: %s", item.id, msg)

                except Exception as e:
                    msg = str(e)
                    queue_manager.update_item_status(item.id, "failed", error=msg)
                    results.append({"id": item.id, "status": "failed", "error": msg})
                    logger.error("Item %s raised exception: %s", item.id, msg)

    return results


def run_execute_confirmed() -> list[dict]:
    """Synchronous wrapper for use from threads (e.g. watchdog callback)."""
    return asyncio.run(execute_confirmed())
