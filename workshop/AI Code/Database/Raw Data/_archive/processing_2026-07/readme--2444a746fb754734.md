# Agentic-Calendar

Hi Here is the youtoube link to my video 

https://youtu.be/6qpjMk6xUoE

# Planning Assistant

A local macOS chat-based planning assistant that connects to Apple Calendar and Apple Reminders via AppleScript. Conversations flow through a three-mode state machine — chat, planning, and implementation — and nothing touches your calendar without your explicit confirmation. Session memory is saved as markdown files between sessions.

---

## What It Does

- **Conversational planning** — chat naturally, and the assistant crystallises tasks into a structured plan when something concrete emerges
- **Explicit planning card** — the plan is surfaced visibly; you can edit it via chat, walk through it, or cancel before anything is written
- **Apple Calendar & Reminders integration** — creates events, all-day events, reminders, and can reschedule existing items
- **Daily scan** — reads your next 7 days of calendar events and all open reminders, runs pre-analysis for missed todos, conflicts, and overloaded days, and proposes a reshuffle you can confirm or dismiss
- **Session memory** — each session is saved to `/memory/` as a markdown file; carry-forward notes and the most recent conversation are injected into future sessions

---

## Prerequisites

- **macOS** (AppleScript is required — this will not run on Linux or Windows)
- **Python 3.10+**
- **PyObjC** (`pyobjc-framework-Cocoa`) — used to run AppleScript via `NSTask` instead of `subprocess` (avoids a `fork()` crash with the OpenAI SDK on macOS)
- **Apple Calendar and Apple Reminders** with Automation permissions granted to your Python process (System Settings → Privacy & Security → Automation)
- An **OpenAI API key**

---

## Installation

```bash
git clone <repo-url>
cd planning-assistant
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-...
APPLE_CALENDAR_NAME=Calendar        # must match your actual calendar name exactly
APPLE_REMINDER_LIST=Work Tracker    # must match your actual Reminders list name exactly
```

> **Important:** The calendar and reminder list names are case-sensitive and must match what appears in Apple Calendar and Reminders exactly. A mismatch causes silent routing to the wrong list.

---

## Running

```bash
python app.py
```

This starts a FastAPI server (default port 8000) and serves the UI at `http://localhost:8000`. Open that URL in your browser.

Alternatively:

```bash
uvicorn app:app --reload
```

---

## Architecture

```
Browser (static/index.html)
    │
    ▼
FastAPI (app.py)  ─── in-memory session state
    │
    ├── planner.py      LLM calls (chat, planning, editing, walkthrough)
    ├── scan.py         Daily scan pipeline (read → pre-analyse → LLM → propose)
    ├── memory.py       Session save/load (markdown files in /memory/)
    ├── daily.py        Alternative daily briefing (currently not wired to UI)
    │
    ├── apple_calendar.py   AppleScript: create/move events, read week/today
    └── apple_reminders.py  AppleScript: create/list/update/clear reminders
```

### The Three Modes

| Mode | What happens |
|---|---|
| **Chat** | Open-ended conversation. The assistant listens, asks questions, and builds context. It never auto-transitions to planning — it always asks first. |
| **Planning** | A structured plan card is rendered. You can edit via chat (`"move the Raj meeting to Thursday"`), ask for a walkthrough, or confirm. Nothing is written yet. |
| **Implementation** | The confirmed plan is executed: AppleScript writes to Apple Calendar and Reminders. Returns to chat after completion. |

### Session State

All state is in-memory in a single `session` dict. The server is **single-user by design** — concurrent requests or multiple browser tabs will corrupt state. State survives requests but is lost on process restart (except what was persisted to `/memory/`).

---

## Module Reference

| File | Purpose |
|---|---|
| `app.py` | FastAPI server, HTTP endpoints, mode state machine, dispatch logic |
| `planner.py` | All LLM calls: chat turns, plan creation, plan editing, walkthrough, direct action extraction |
| `scan.py` | Daily scan: reads full week of events + all reminders, pre-analysis, LLM briefing, reshuffle proposal |
| `daily.py` | Simpler daily briefing (reads today only, writes to "Today" Reminders list) — not currently wired to the UI |
| `memory.py` | Saves sessions to `/memory/*.md`; loads recent carry-forward notes and last conversation on startup |
| `apple_calendar.py` | AppleScript interface for Apple Calendar (create, move, read) |
| `apple_reminders.py` | AppleScript interface for Apple Reminders (create, list, update, complete, clear) |

---

## Key Endpoints

| Endpoint | What it does |
|---|---|
| `GET /` | Serves the UI (`static/index.html`) |
| `POST /chat` | Main chat endpoint — all user messages go here |
| `POST /confirm` | Executes the current plan (writes to Calendar/Reminders) |
| `POST /confirm_direct` | Confirms a single pending direct action (event or reminder) |
| `POST /cancel_direct` | Cancels a pending direct action without writing |
| `POST /walkthrough` | Returns a narration of the current plan |
| `POST /backward` | Returns to chat mode, preserving the current plan |
| `POST /daily` | Runs the daily scan |
| `POST /new_session` | Saves the current session to disk and resets state |
| `GET /state` | Returns the full session dict (no authentication — local use only) |

---

## Session Memory

Sessions are saved to `/memory/` as markdown files named `YYYY-MM-DD_HH-MM_<auto-title>.md`. The auto-title is a 3–5 word slug generated by the LLM from the session content.

On startup, the loader:
1. Collects carry-forward notes from all sessions in the last 7 days
2. Includes the full conversation from the most recent session
3. Caps the total at approximately 2000 tokens (~8000 characters)
4. Injects the result into the LLM system prompt

Memory files are never auto-deleted. The loading strategy naturally ignores old files.

---

## Daily Scan

Triggered via the **Daily Check** button in the UI. Reads all Apple Calendar events for the next 7 days and all open reminders across every list, then:

- Flags **missed todos** — reminders with a due date in the past
- Flags **orphaned todos** — reminders with no due date
- Detects **calendar conflicts** — overlapping timed events on the same day
- Flags **overloaded days** — days with more than 4 events

The LLM receives both the raw data and this pre-analysis, then returns a conversational morning briefing and optionally a reshuffle plan. The plan renders as a planning card — same confirm flow as regular planning. Nothing is moved or created until you confirm.

---

## Known Issues & Limitations

**Before testing, fix the model name.** The current codebase references `"gpt-5.4-nano"` in four files — this is not a valid OpenAI model ID and will cause all LLM calls to fail at runtime. Change it to `"gpt-4o"` or `"gpt-4o-mini"` in:

- `planner.py`
- `scan.py`
- `memory.py`
- `daily.py`

Other known issues:

- **Single-user only** — the in-memory session dict is shared; concurrent requests will corrupt state
- **No write rollback** — if a plan with 5 items fails on item 3, items 1 and 2 are already written to Calendar/Reminders with no undo
- **No de-duplication** — confirming the same plan twice creates duplicate events and reminders
- **Orphaned todo age detection is non-functional** — Apple Reminders does not expose reminder creation dates reliably; age-based flagging is not implemented
- **`daily.py` is not wired to the UI** — the `/daily` endpoint calls `scan.py`'s pipeline instead; `daily.py` may be legacy code
- **`move_event` does not preserve original duration** — moved events default to 60 minutes if the plan does not specify `duration_minutes`
- **Event titles containing `|`** will corrupt the pipe-delimited output from `get_week_events` and `get_today_events`
- **Session messages grow unbounded** — no trimming; very long sessions will eventually hit OpenAI's context window limit

---

## Permissions

On first run, macOS will prompt for Automation permissions. Grant access to both **Calendar** and **Reminders** when prompted, or go to System Settings → Privacy & Security → Automation and enable both for your terminal / Python process.

If AppleScript calls fail with a permissions error, this is the most likely cause.

---

## Development Notes

- `apple_calendar.py` and `apple_reminders.py` use `NSTask` (PyObjC) rather than `subprocess` to avoid a `fork()` crash that occurs when the OpenAI SDK and `subprocess` are combined on macOS. Do not switch to `subprocess` without understanding this constraint.
- Any synchronous blocking call (AppleScript, file I/O) inside an `async def` FastAPI handler must be wrapped in `asyncio.to_thread()`.
- When adding a new task action type, update both the `confirm()` handler in `app.py` and the system prompt in `scan.py` (`_SCAN_SYSTEM`) — they must stay in sync.
- The `_DIRECT_KEYWORDS` list in `app.py` and the direct-action descriptions in `planner.py`'s system prompt must stay in sync.
- All string parameters interpolated into AppleScript f-strings must be escaped with `.replace('"', '\\"')` before interpolation.

---

## Future Plans

- Replace the static HTML frontend with a WhatsApp integration (same Python backend, swap I/O layer)
- Add Slack / email integration for follow-up tracking
- Session search: query `/memory/` by topic keyword



