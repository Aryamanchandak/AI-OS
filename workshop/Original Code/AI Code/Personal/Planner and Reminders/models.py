# Version: V2
"""
Pydantic V2 models for every data boundary in the planner system.

Boundaries:
  1. planner.py → queue_manager: LLM tool args validated before queue write
  2. queue_manager → executor: raw JSON validated before MCP call
  3. mcp_server: MCP arguments validated before AppleScript call
  4. app.py FastAPI: all request/response bodies

ID scheme:
  evt_NNN  — create_event items
  rem_NNN  — create_reminder items
  act_NNN  — move/edit/delete items

Note: date/time/datetime are imported with aliases (Date/Time/DateTime)
to avoid shadowing by field names 'date' and 'time' in subclasses.
"""

from __future__ import annotations

from datetime import date as Date, time as Time, datetime as DateTime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


# ── Read result models ────────────────────────────────────────────────────────

class CalendarEvent(BaseModel):
    title: str
    date: Date
    start: Time | None = None
    end: Time | None = None
    allday: bool = False


class Reminder(BaseModel):
    title: str
    due: Date | None = None
    due_time: Time | None = None
    list_name: str
    description: str = ""


# ── Queue item base ───────────────────────────────────────────────────────────

class QueueItemBase(BaseModel):
    id: str
    status: Literal["proposed", "confirmed", "done", "failed"]
    created_at: DateTime
    confirmed_at: DateTime | None = None
    executed_at: DateTime | None = None
    error: str | None = None


# ── Create items ──────────────────────────────────────────────────────────────

class CreateEventItem(QueueItemBase):
    type: Literal["create_event"]
    title: str
    date: Date
    time: Time | None = None       # None = all-day
    duration_minutes: int = 60
    description: str = ""


class CreateReminderItem(QueueItemBase):
    type: Literal["create_reminder"]
    title: str
    date: Date
    time: Time                     # always required — sets the alert
    description: str = ""


# ── Edit / move / delete items ────────────────────────────────────────────────

class MoveEventItem(QueueItemBase):
    type: Literal["move_event"]
    original_title: str
    original_date: Date
    original_start: Time
    new_date: Date
    new_start: Time
    duration_minutes: int = 60


class EditEventItem(QueueItemBase):
    type: Literal["edit_event"]
    title: str
    date: Date
    new_title: str | None = None
    new_description: str | None = None
    new_duration_minutes: int | None = None


class UpdateReminderItem(QueueItemBase):
    type: Literal["update_reminder_date"]
    title: str
    list_name: str
    new_date: Date
    new_time: Time | None = None


class EditReminderItem(QueueItemBase):
    type: Literal["edit_reminder"]
    title: str
    list_name: str
    new_title: str | None = None
    new_description: str | None = None


class DeleteEventItem(QueueItemBase):
    type: Literal["delete_event"]
    title: str
    date: Date


class DeleteReminderItem(QueueItemBase):
    type: Literal["delete_reminder"]
    title: str
    list_name: str


# ── Discriminated union for queue parsing ─────────────────────────────────────

QueueItem = Annotated[
    CreateEventItem
    | CreateReminderItem
    | MoveEventItem
    | EditEventItem
    | UpdateReminderItem
    | EditReminderItem
    | DeleteEventItem
    | DeleteReminderItem,
    Field(discriminator="type"),
]


# ── FastAPI request / response bodies ─────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class QueueStatusItem(BaseModel):
    id: str
    type: str
    status: Literal["proposed", "confirmed", "done", "failed"]
    title: str | None = None       # human-readable label; computed from item fields
    error: str | None = None


class QueueStatusResponse(BaseModel):
    items: list[QueueStatusItem]
    pending_count: int
    done_count: int
    failed_count: int
