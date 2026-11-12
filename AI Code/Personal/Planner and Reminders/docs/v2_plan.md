# Plan: Two-Agent MCP Architecture with Queue-Based Execution

## Context
Redesign from a single agent that both plans AND executes, to two independent agent sets communicating via a file-based queue (`queue.md`). The frontend agent writes structured intent; the executor processes confirmed items via a complete MCP server wrapping AppleScript. The MCP server is the single integration point for all Apple Calendar / Apple Reminders operations — reads, creates, and edits are three distinct categories.

---

## Architecture

```
User → Frontend Agent (OpenAI GPT-4o, function calling)
         │
         ├── Read tools → MCP server "read" tools (get_calendar_events, get_reminders)
         │                  ↓ direct call, no queue
         │               apple_calendar.py / apple_reminders.py
         │
         └── Write/Edit tools → validate with Pydantic V2
                                  ↓ append "proposed" item to queue.md
                               User confirms in UI
                                  ↓ status flips to "confirmed"
                               Executor (watchdog watcher)
                                  ↓ reads confirmed items (Pydantic V2)
                               MCP server "create" / "edit" tools
                                  ↓ MCP tool call
                               apple_calendar.py / apple_reminders.py
                                  ↓ status → "done" / "failed"
                               queue.md → frontend polls → shows result
```

---

## MCP Server Tool Categories

The MCP server (`mcp_server/applescript_mcp.py`) exposes **three distinct categories**:

### 1. Read Tools (no queue, auto-execute)
These are called directly by the frontend agent (and by any future MCP client). They never touch the queue.

| Tool | Description |
|------|-------------|
| `get_calendar_events(days_ahead: int = 7)` | Returns all events for the next N days |
| `get_reminders(list_name: str \| None)` | Returns all open reminders, optionally filtered by list |

### 2. Create Tools (queue → confirmed → executor)
New items only — the item does not yet exist in Calendar/Reminders.

| Tool | Description |
|------|-------------|
| `create_event(title, date, time, duration_minutes, description, calendar_name)` | Creates a new calendar event |
| `create_reminder(title, date, time, description, list_name)` | Creates a new reminder with alert |

### 3. Edit Tools (queue → confirmed → executor)
Mutations on items that already exist. Separate from creation — different UX confirmation, different AppleScript calls, different Pydantic models.

| Tool | Description |
|------|-------------|
| `move_event(original_title, original_date, original_start, new_date, new_start, duration_minutes)` | Reschedule an event to a new date/time |
| `edit_event(title, date, new_title?, new_description?, new_duration_minutes?)` | Edit properties of an existing event without moving it |
| `update_reminder_date(title, list_name, new_date, new_time?)` | Reschedule a reminder's due date/time |
| `edit_reminder(title, list_name, new_title?, new_description?)` | Edit a reminder's content without changing its date |
| `delete_event(title, date)` | Delete a calendar event |
| `delete_reminder(title, list_name)` | Delete a reminder |

---

## Pydantic V2 Boundaries

All models live in `models.py`. Every data crossing a boundary is validated — no raw dicts.

### Queue Item Models

```python
# -- Read result models (returned by MCP read tools) --
class CalendarEvent(BaseModel):
    title: str
    date: date
    start: time | None = None
    end: time | None = None
    allday: bool = False

class Reminder(BaseModel):
    title: str
    due: date | None = None
    due_time: time | None = None
    list_name: str
    description: str = ""

# -- Queue item base --
class QueueItemBase(BaseModel):
    id: str
    status: Literal["proposed", "confirmed", "done", "failed"]
    created_at: datetime
    confirmed_at: datetime | None = None
    executed_at: datetime | None = None
    error: str | None = None

# -- Create items --
class CreateEventItem(QueueItemBase):
    type: Literal["create_event"]
    title: str
    date: date
    time: time | None = None        # None = all-day
    duration_minutes: int = 60
    description: str = ""

class CreateReminderItem(QueueItemBase):
    type: Literal["create_reminder"]
    title: str
    date: date
    time: time                      # always required — sets the alert
    description: str = ""

# -- Edit items --
class MoveEventItem(QueueItemBase):
    type: Literal["move_event"]
    original_title: str
    original_date: date
    original_start: time
    new_date: date
    new_start: time
    duration_minutes: int = 60

class EditEventItem(QueueItemBase):
    type: Literal["edit_event"]
    title: str
    date: date
    new_title: str | None = None
    new_description: str | None = None
    new_duration_minutes: int | None = None

class UpdateReminderItem(QueueItemBase):
    type: Literal["update_reminder_date"]
    title: str
    list_name: str
    new_date: date
    new_time: time | None = None

class EditReminderItem(QueueItemBase):
    type: Literal["edit_reminder"]
    title: str
    list_name: str
    new_title: str | None = None
    new_description: str | None = None

class DeleteEventItem(QueueItemBase):
    type: Literal["delete_event"]
    title: str
    date: date

class DeleteReminderItem(QueueItemBase):
    type: Literal["delete_reminder"]
    title: str
    list_name: str

# -- Discriminated union for queue parsing --
QueueItem = Annotated[
    CreateEventItem | CreateReminderItem | MoveEventItem | EditEventItem |
    UpdateReminderItem | EditReminderItem | DeleteEventItem | DeleteReminderItem,
    Field(discriminator="type")
]
```

**Boundaries where Pydantic validates:**
1. `planner.py` → write tools: LLM tool-call args → `CreateEventItem(**args)` before appending to queue
2. `executor.py` → reads queue: raw JSON → `TypeAdapter(QueueItem).validate_python(raw)` before processing
3. `mcp_server/applescript_mcp.py` → each tool call: MCP arguments re-validated against the relevant model before calling AppleScript
4. `app.py` → all FastAPI request/response bodies are `BaseModel` subclasses

---

## Queue MD File Format (fixed schema)

**File:** `queue.md` (project root, auto-created by `queue_manager.py`)

One `## <id>` section per item. The JSON block is the single source of truth — the heading is human-readable only.

```markdown
# Planner Action Queue

## evt_001
```json
{
  "id": "evt_001",
  "type": "create_event",
  "status": "confirmed",
  "title": "Team Standup",
  "date": "2026-06-15",
  "time": "09:00",
  "duration_minutes": 30,
  "description": "",
  "created_at": "2026-06-14T10:28:00",
  "confirmed_at": "2026-06-14T10:29:00",
  "executed_at": null,
  "error": null
}
```

## rem_001
```json
{
  "id": "rem_001",
  "type": "create_reminder",
  "status": "proposed",
  "title": "Send Raj the deck",
  "date": "2026-06-15",
  "time": "09:00",
  "description": "The Q2 investor deck — final version",
  "created_at": "2026-06-14T10:30:00",
  "confirmed_at": null,
  "executed_at": null,
  "error": null
}
```

## act_001
```json
{
  "id": "act_001",
  "type": "move_event",
  "status": "done",
  "original_title": "1:1 with Priya",
  "original_date": "2026-06-15",
  "original_start": "14:00",
  "new_date": "2026-06-16",
  "new_start": "10:00",
  "duration_minutes": 60,
  "created_at": "2026-06-14T11:00:00",
  "confirmed_at": "2026-06-14T11:01:00",
  "executed_at": "2026-06-14T11:01:05",
  "error": null
}
```
```

**Parse strategy:** Extract all ` ```json ... ``` ` blocks; parse each with `TypeAdapter(QueueItem).validate_python()`; filter by status.

**ID scheme:** `evt_NNN` (create event), `rem_NNN` (create reminder), `act_NNN` (all edits/deletes). Sequential, scanned from existing `queue.md` on startup.

---

## Frontend Agent Changes (planner.py)

The write tool section of `execute_tool()` becomes:

```python
# write tools no longer call AppleScript — they write to queue
elif name == "create_event":
    item = CreateEventItem(id=next_id("evt"), type="create_event",
                           status="proposed", created_at=datetime.now(), **args)
    queue_manager.append_item(item)
    return f"Queued: create event '{item.title}' on {item.date}"

elif name == "create_reminder":
    item = CreateReminderItem(id=next_id("rem"), type="create_reminder",
                              status="proposed", created_at=datetime.now(), **args)
    queue_manager.append_item(item)
    return f"Queued: reminder '{item.title}' due {item.date} at {item.time}"
# ... same pattern for move_event, edit_event, etc.
```

Read tools (`check_calendar`, `check_reminders`) continue calling AppleScript functions directly — fast path, no queue.

---

## App.py Changes

- `/confirm_action`: call `queue_manager.confirm_all_proposed()` (flips status, triggers watcher) instead of `execute_tool()`
- `/cancel_action`: call `queue_manager.remove_proposed()` instead of clearing session state
- `/queue_status` (new GET): returns `{"items": [{"id", "status", "error"}]}` for all non-done/proposed items
- Lifespan: after loading memory, start `QueueWatcher` as a `threading.Thread(daemon=True)`

---

## Executor Flow

```
watchdog fires on queue.md change
  → executor reads queue.md
  → filter: status == "confirmed"
  → for each confirmed item:
      1. TypeAdapter(QueueItem).validate_python(raw_json)
      2. spawn MCP server subprocess (asyncio.create_subprocess_exec, not fork)
      3. call matching MCP tool with item's fields
      4. on success: update item status → "done", set executed_at
      5. on failure: update item status → "failed", set error message
  → write updated queue.md (file-locked during write)
```

Self-trigger guard: before processing, check if any `confirmed` items exist. If the watcher fired because the executor itself wrote `done`/`failed`, there will be no `confirmed` items — exit early.

---

## Files to Create

| File | Purpose |
|------|---------|
| `models.py` | All Pydantic V2 models: queue items, read results, API shapes |
| `queue_manager.py` | `append_item()`, `confirm_all_proposed()`, `remove_proposed()`, `update_item()`, `list_by_status()`, file locking |
| `mcp_server/__init__.py` | Package marker |
| `mcp_server/applescript_mcp.py` | Complete MCP server: 2 read + 2 create + 6 edit tools |
| `executor/__init__.py` | Package marker |
| `executor/queue_watcher.py` | watchdog FSEventsObserver on queue.md |
| `executor/executor.py` | MCP client + deterministic queue processor |

## Files to Modify

| File | Changes |
|------|---------|
| `app.py` | Restore from git; update `/confirm_action`, `/cancel_action`; add `/queue_status`; start watcher in lifespan |
| `planner.py` | Write tools → `queue_manager.append_item()`; read tools unchanged |
| `static/index.html` | Poll `/queue_status` after confirm; show per-item done/failed inline in chat |
| `requirements.txt` | Add `mcp>=1.0`, `watchdog>=4.0` |

Also add `edit_event()` and `edit_reminder()` functions to `apple_calendar.py` and `apple_reminders.py` (currently only move/update-date exist).

---

## Startup

1. `uvicorn app:app --port 8000` starts FastAPI
2. Lifespan: load memory → start `QueueWatcher` daemon thread
3. MCP server is spawned **on demand** by executor (short-lived subprocess per execution batch, stdio transport, no persistent process)

---

## Verification

1. `pip install mcp watchdog` — no import errors
2. Start server: `cd "Calendar and Reminders" && python -m uvicorn app:app --port 8000`
3. **Create flow**: "Remind me to send Raj the deck tomorrow at 9am" → proposed in queue.md → confirm → watch queue.md: `proposed → confirmed → done` → verify reminder appears in Apple Reminders
4. **Edit flow**: "Move tomorrow's standup to 10am" → proposed edit item in queue.md → confirm → done → verify in Apple Calendar
5. **Read flow**: "What's on my calendar this week?" → MCP read tool called directly → no queue entry created
6. **Cancel flow**: propose item → cancel → item removed from queue.md → nothing appears in Calendar/Reminders
7. **Error flow**: bad calendar name → status flips to `failed`, error surfaced in chat
8. **Pydantic rejection**: manually pass reminder without `time` field → Pydantic raises `ValidationError` before queue write
