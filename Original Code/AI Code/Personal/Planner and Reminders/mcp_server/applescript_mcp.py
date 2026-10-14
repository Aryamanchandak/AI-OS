# Version: V2
"""
MCP server wrapping Apple Calendar and Apple Reminders via AppleScript.

Three tool categories:
  READ   — get_calendar_events, get_reminders          (no queue, safe to call anytime)
  CREATE — create_event, create_reminder               (called by executor on confirmed queue items)
  EDIT   — move_event, edit_event, update_reminder_date,
            edit_reminder, delete_event, delete_reminder

Run as a subprocess (stdio transport). The executor spawns this on demand.

Usage:
  python -m mcp_server.applescript_mcp
"""

import sys
import os

# Allow imports from project root when run as a subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from pydantic import ValidationError

import apple_calendar
import apple_reminders
from models import (
    CalendarEvent,
    Reminder,
    CreateEventItem,
    CreateReminderItem,
    MoveEventItem,
    EditEventItem,
    UpdateReminderItem,
    EditReminderItem,
    DeleteEventItem,
    DeleteReminderItem,
)

CALENDAR_NAME = os.getenv("APPLE_CALENDAR_NAME", "Calendar")
REMINDER_LIST = os.getenv("APPLE_REMINDER_LIST", "Work Tracker")

server = Server("planner-applescript")


# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── READ ─────────────────────────────────────────────────────────────
        types.Tool(
            name="get_calendar_events",
            description="Read calendar events for the next N days. Returns title, date, start, end, allday.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "default": 7, "description": "Days to look ahead (1 = today only)"},
                    "calendar_name": {"type": "string", "description": "Calendar name. Uses default if omitted."},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_reminders",
            description="Read all open (incomplete) reminders, optionally filtered by list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "list_name": {"type": "string", "description": "Filter to a specific list. Omit for all lists."},
                },
                "required": [],
            },
        ),
        # ── CREATE ───────────────────────────────────────────────────────────
        types.Tool(
            name="create_event",
            description="Create a new calendar event.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM 24h. Omit for all-day."},
                    "duration_minutes": {"type": "integer", "default": 60},
                    "description": {"type": "string", "default": ""},
                    "calendar_name": {"type": "string"},
                },
                "required": ["title", "date"],
            },
        ),
        types.Tool(
            name="create_reminder",
            description="Create a new reminder with a timed alert.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM 24h — required, sets the alert time"},
                    "description": {"type": "string", "default": ""},
                    "list_name": {"type": "string"},
                },
                "required": ["title", "date", "time"],
            },
        ),
        # ── EDIT ─────────────────────────────────────────────────────────────
        types.Tool(
            name="move_event",
            description="Reschedule an existing calendar event to a new date/time.",
            inputSchema={
                "type": "object",
                "properties": {
                    "original_title": {"type": "string"},
                    "original_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "original_start": {"type": "string", "description": "HH:MM"},
                    "new_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "new_start": {"type": "string", "description": "HH:MM"},
                    "duration_minutes": {"type": "integer", "default": 60},
                    "calendar_name": {"type": "string"},
                },
                "required": ["original_title", "original_date", "original_start", "new_date", "new_start"],
            },
        ),
        types.Tool(
            name="edit_event",
            description="Edit an existing event's title, description, or duration without rescheduling.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Current event title"},
                    "date": {"type": "string", "description": "YYYY-MM-DD of the event"},
                    "new_title": {"type": "string"},
                    "new_description": {"type": "string"},
                    "new_duration_minutes": {"type": "integer"},
                    "calendar_name": {"type": "string"},
                },
                "required": ["title", "date"],
            },
        ),
        types.Tool(
            name="update_reminder_date",
            description="Reschedule a reminder's due date and optionally its alert time.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "list_name": {"type": "string"},
                    "new_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "new_time": {"type": "string", "description": "HH:MM — omit to keep midnight"},
                },
                "required": ["title", "list_name", "new_date"],
            },
        ),
        types.Tool(
            name="edit_reminder",
            description="Edit a reminder's title or body without changing its due date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "list_name": {"type": "string"},
                    "new_title": {"type": "string"},
                    "new_description": {"type": "string"},
                },
                "required": ["title", "list_name"],
            },
        ),
        types.Tool(
            name="delete_event",
            description="Delete a calendar event by title and date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "calendar_name": {"type": "string"},
                },
                "required": ["title", "date"],
            },
        ),
        types.Tool(
            name="delete_reminder",
            description="Delete a reminder by title and list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "list_name": {"type": "string"},
                },
                "required": ["title", "list_name"],
            },
        ),
    ]


# ── Tool dispatch ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    try:
        result = await asyncio.to_thread(_dispatch, name, arguments)
        return [types.TextContent(type="text", text=result)]
    except (ValidationError, ValueError, RuntimeError) as e:
        return [types.TextContent(type="text", text=f"ERROR: {e}")]


def _dispatch(name: str, args: dict[str, Any]) -> str:
    """Synchronous dispatch — runs in a thread."""
    cal = args.get("calendar_name", CALENDAR_NAME)
    lst = args.get("list_name", REMINDER_LIST)

    # ── READ ─────────────────────────────────────────────────────────────────
    if name == "get_calendar_events":
        days = args.get("days_ahead", 7)
        if days <= 1:
            raw = apple_calendar.get_today_events(cal)
        else:
            raw = apple_calendar.get_week_events(cal)
        events = [CalendarEvent(**e) for e in raw]
        return "\n".join(
            f"{e.date} {e.start or 'all-day'} — {e.title}" for e in events
        ) or "No events found."

    if name == "get_reminders":
        filter_list = args.get("list_name")
        if filter_list:
            raw = apple_reminders.list_open_reminders(filter_list)
            items = [Reminder(title=r["title"], due=r.get("due"), list_name=filter_list) for r in raw]
        else:
            raw = apple_reminders.list_all_open_reminders()
            items = [
                Reminder(
                    title=r["title"],
                    due=r.get("due"),
                    list_name=r["list"],
                )
                for r in raw
            ]
        return "\n".join(
            f"{r.list_name} | {r.due or 'no date'} — {r.title}" for r in items
        ) or "No open reminders."

    # ── CREATE ───────────────────────────────────────────────────────────────
    if name == "create_event":
        time_val = args.get("time")
        if time_val:
            apple_calendar.create_timed_event(
                args["title"], args["date"], time_val,
                args.get("duration_minutes", 60),
                args.get("description", ""), cal,
            )
        else:
            apple_calendar.create_allday_event(
                args["title"], args["date"],
                args.get("description", ""), cal,
            )
        return f"Created event: {args['title']} on {args['date']}"

    if name == "create_reminder":
        apple_reminders.ensure_list(lst)
        apple_reminders.create_reminder(
            args["title"],
            args.get("description", ""),
            args["date"],
            lst,
            args.get("time", ""),
        )
        return f"Created reminder: {args['title']} due {args['date']} at {args.get('time', 'midnight')}"

    # ── EDIT ─────────────────────────────────────────────────────────────────
    if name == "move_event":
        apple_calendar.move_event(
            args["original_title"], args["original_date"], args["original_start"],
            args["new_date"], args["new_start"],
            args.get("duration_minutes", 60), cal,
        )
        return f"Moved '{args['original_title']}' to {args['new_date']} {args['new_start']}"

    if name == "edit_event":
        apple_calendar.edit_event(
            args["title"], args["date"], cal,
            new_title=args.get("new_title"),
            new_description=args.get("new_description"),
            new_duration_minutes=args.get("new_duration_minutes"),
        )
        return f"Edited event: {args['title']} on {args['date']}"

    if name == "update_reminder_date":
        apple_reminders.update_reminder_date(
            args["title"], lst, args["new_date"],
            args.get("new_time", ""),
        )
        return f"Updated reminder '{args['title']}' → {args['new_date']}"

    if name == "edit_reminder":
        apple_reminders.edit_reminder(
            args["title"], lst,
            new_title=args.get("new_title"),
            new_description=args.get("new_description"),
        )
        return f"Edited reminder: {args['title']}"

    if name == "delete_event":
        apple_calendar.delete_event(args["title"], args["date"], cal)
        return f"Deleted event: {args['title']} on {args['date']}"

    if name == "delete_reminder":
        apple_reminders.delete_reminder(args["title"], lst)
        return f"Deleted reminder: {args['title']}"

    raise ValueError(f"Unknown tool: {name}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
