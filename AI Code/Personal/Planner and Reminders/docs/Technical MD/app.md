# app.py — Technical Documentation

**Last updated:** 2026-04-24
**Lines of code:** 365
**Language:** Python (FastAPI)

---

## What This File Does (Plain English)

This is the application entry point and HTTP API server. It serves a static HTML frontend, owns the in-memory session state for a single user, and routes all interactions through a FastAPI endpoint layer. It coordinates five other modules — the agent loop in `planner.py`, the AppleScript layers in `apple_calendar.py` and `apple_reminders.py`, the daily scanner in `scan.py`, and the memory system in `memory.py`. Every user action hits an endpoint defined here: sending a chat message, confirming or cancelling proposed write actions, running the daily scan, or starting a new session.

---

## How It Actually Works

### Entry Points

- **`uvicorn app:app`** starts the server (or `python app.py` which calls `uvicorn.run` on `127.0.0.1:8000`).
- **`GET /`** serves `static/index.html` — the entire UI is a static file.
- **`GET /state`** returns current session state (messages, pending actions) for page reload recovery.
- **`POST /chat`** is the main interaction endpoint, called on every user message.
- **`POST /confirm_action`** executes pending write tool calls after user approval.
- **`POST /cancel_action`** discards pending write tool calls with no writes.
- **`POST /daily`** triggers the daily scan pipeline.
- **`POST /new_session`** saves the current session to memory and resets state.
- **Lifespan handler** (`asynccontextmanager lifespan`) loads memory context on startup, loads any pending state persisted to `pending_state.json`, and saves the session to memory on clean shutdown.

### Data Flow

**On startup (lifespan):**
1. `load_memory_context()` reads recent memory files from the Obsidian vault directory, stores result in `session["memory_context"]`.
2. `_load_pending_state()` reads `pending_state.json` if it exists, restoring `pending_actions`, `pending_assistant_msg`, and `messages` — so the confirmation card survives a server restart between when the user sees a proposal and when they click confirm.

**On `POST /chat`:**
1. User message appended to `session["messages"]`.
2. `_build_oai_messages()` constructs the full OpenAI message list: calls `_get_today_calendar_context()` (live AppleScript read), injects today's events into the system prompt via `build_system_messages()`, then converts all session messages to OpenAI format.
3. `run_agent_loop()` is called in a thread (`asyncio.to_thread`) with the full message history.
4. If the agent loop returns `pending_actions`, they are stored in session state and written to `pending_state.json` for crash recovery.
5. The agent's reply and any pending action metadata are returned to the frontend.

**On `POST /confirm_action`:**
1. Iterates `session["pending_actions"]` in order.
2. For each action, calls `execute_tool()` to perform the write via AppleScript.
3. Builds a rollback stack: `create_event` → `delete_event`, `create_reminder` → `delete_reminder`, `move_event` → `move_event_back`.
4. If any action fails, iterates the rollback stack in reverse and attempts to undo all previously committed actions.
5. Clears pending state from session and from `pending_state.json`.
6. If all actions succeeded, re-enters the agent loop with the full tool results so the model can chain further actions or produce a summary reply.
7. The response may itself contain new pending actions (multi-step chaining).

**On `POST /daily`:**
1. `run_daily_scan()` is called in a thread (`asyncio.to_thread`).
2. Result has the same shape as `run_agent_loop`: `{reply, pending_actions, assistant_msg}`.
3. If there are pending actions, they are stored in session and persisted.

**On `POST /new_session`:**
1. Saves current session via `save_session()`.
2. Clears `pending_state.json`.
3. Resets session dict to initial values, freshly loading memory context.

### State Management

All state lives in a single module-level `session` dict — **not in a database, not per-request, not per-user**. This is explicitly single-user. Concurrent requests will corrupt state.

| Key | Type | Purpose |
|---|---|---|
| `messages` | `list[dict]` | Full conversation history, `{role, content}` where role is `"user"` or `"ai"` |
| `oai_messages` | `list[dict]` | Placeholder — rebuilt fresh each `/chat` call, not meaningfully maintained |
| `pending_actions` | `list[dict]` | Write tool calls awaiting user confirmation, each `{name, args, call_id}` |
| `pending_assistant_msg` | `dict \| None` | The assistant message with `tool_calls` field — needed to resume the agent loop after confirmation |
| `session_start_time` | `datetime` | Used to name the memory file on session save |
| `memory_context` | `str` | Pre-loaded text from memory files, injected into every system prompt |

### Pending-State Persistence

Three private functions manage `pending_state.json` in the project root:
- `_save_pending_state()` — writes `pending_actions`, `pending_assistant_msg`, and `messages` to disk. Called after any endpoint that produces pending actions.
- `_load_pending_state()` — reads on startup. Restores the state so a confirmation card survives a server crash between proposal and confirm.
- `_clear_pending_state()` — deletes the file. Called on confirm, cancel, and new_session.

All three swallow exceptions silently.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `_save_pending_state()` | Writes pending actions and messages to `pending_state.json`. Silent on failure. |
| `_clear_pending_state()` | Deletes `pending_state.json`. Silent on failure. |
| `_load_pending_state()` | Reads `pending_state.json` on startup to restore confirmation state across restarts. |
| `_get_today_calendar_context()` | Calls `get_today_events()` and formats the result as a bullet list for system prompt injection. Returns empty string on failure. |
| `_build_oai_messages()` | Builds the full OpenAI message list: system prompt with today's date + calendar context + optional memory block + conversation history. Called on every `/chat` and on confirm's resume path. |
| `_actions_to_frontend(actions)` | Converts internal `{name, args, call_id}` dicts to a simpler `{tool, ...args}` shape for the frontend. |
| `chat()` (`POST /chat`) | Appends user message, calls `run_agent_loop`, stores any pending actions, returns reply + action card data. |
| `confirm_action()` (`POST /confirm_action`) | Executes all pending write tools with rollback on failure, then re-enters agent loop with tool results. |
| `cancel_action()` (`POST /cancel_action`) | Clears pending actions with no writes, appends cancellation message. |
| `daily()` (`POST /daily`) | Runs `run_daily_scan` in a thread, stores any pending actions from it. |
| `new_session()` (`POST /new_session`) | Saves session, clears pending state, resets all session keys with fresh memory load. |
| `lifespan(app)` | FastAPI lifespan: loads memory and pending state on startup, saves session on clean shutdown. |

### External Dependencies

- **`planner.py`** — `run_agent_loop`, `execute_tool`, `build_system_messages`
- **`apple_calendar.py`** — `get_today_events`, `delete_event`, `move_event` (for rollback)
- **`apple_reminders.py`** — `ensure_list`, `delete_reminder` (for rollback)
- **`scan.py`** — `run_daily_scan`
- **`memory.py`** — `load_memory_context`, `save_session`
- **`fastapi`**, **`pydantic`**, **`python-dotenv`**, **`asyncio`**
- **Environment variables:** `OPENAI_API_KEY` (consumed by `planner.py`, `memory.py`, `scan.py`), `APPLE_CALENDAR_NAME` (default: `"Calendar"`), `APPLE_REMINDER_LIST` (default: `"Work Tracker"`)
- **Files:** `BASE_DIR/static/index.html` (served on `GET /`), `BASE_DIR/pending_state.json` (created/deleted dynamically)

### Error Handling

| Failure point | Handling |
|---|---|
| `run_agent_loop()` raises in `/chat` | Not caught in `/chat` handler — propagates as a 500 error to the frontend |
| Any action in `confirm_action()` raises | Rollback attempted for previously-committed actions, error message returned as reply |
| Rollback also fails | Error message notes "Cleanup partial — N undo(s) also failed." |
| Resume agent loop after confirm fails | Writes already committed; reply summarises what was done plus the follow-up error |
| `run_daily_scan()` raises | Caught in `/daily`, returns `{"reply": "Daily scan failed: ..."}` |
| Session save on shutdown or `/new_session` raises | Caught with bare `except Exception: pass` — silent loss |
| `_get_today_calendar_context()` raises | Caught, returns empty string — system prompt gets no calendar context |
| Pending state file I/O fails | All three helpers swallow exceptions silently |

---

## Non-Technical Decisions Embedded in the Code

- **Single-user `session` dict** — module-level, shared across all requests. This is a deliberate simplification: the app is designed for one person on one machine.
- **`asyncio.to_thread()` for all blocking calls** — `run_agent_loop`, `run_daily_scan`, and implicitly any AppleScript calls within them are pushed to threads. This keeps the FastAPI event loop unblocked.
- **Rollback stack tracks only three action types** — `create_event`, `create_reminder`, `move_event`. Other write tools (`update_reminder_date`, `delete_event`) push `None` onto the rollback stack and are not undoable. Deleting an event you just deleted, or re-adding a date to a rescheduled reminder, is not attempted.
- **`REMINDER_LIST` from env is used for all reminder operations** — `ensure_list(REMINDER_LIST)` is called once in `confirm_action` before the loop. The `create_reminder` tool in the agent loop always writes to this single list regardless of what list the user might intend.
- **`modes_visited=["chat"]` is hardcoded** in both `save_session` calls — the old multi-mode tracking is gone. The session file always shows only "chat" in the modes header regardless of what happened.
- **`oai_messages` key in `session`** is initialized but never meaningfully maintained — `_build_oai_messages()` rebuilds it from scratch on every call and the result is not stored back to `session["oai_messages"]`. It is vestigial.
- **`confirm_action` re-enters `run_agent_loop`** after writes succeed — this allows multi-step chains (e.g. the model creates an event and then immediately proposes a reminder for it in the same confirmation flow). This can produce a second pending action card from a single confirm.
- **`pending_assistant_msg` fallback when `None`** — if the server restarts between a write proposal and user confirmation, `pending_assistant_msg` is restored from `pending_state.json`. If that file is also absent, the confirm path falls back to a plain summary without re-entering the agent loop.

---

## Honest Gaps and Risks

- **No authentication on any endpoint** — anyone on the same local network who can reach port 8000 can read session state via `GET /state`, inject messages via `POST /chat`, or confirm actions. Intended for single-user local use only.
- **No de-duplication** — double-clicking "Confirm" creates duplicate calendar events and reminders. `pending_state.json` is cleared immediately at the start of `confirm_action`, so the second click finds no pending actions and returns early — but the first click may have already completed.
- **Rollback is best-effort and not transactional** — if action 2 succeeds and action 3 fails, the rollback attempts to undo actions 1 and 2. If those rollbacks also fail, the user is told some cleanup failed with a count, but not which items are now in an inconsistent state.
- **`session["messages"]` grows unbounded** — no trimming. Long sessions will eventually hit the OpenAI context window limit. The error propagates uncaught from `run_agent_loop` through the `/chat` handler.
- **`get_today_events` returns `start` as a raw AppleScript date string**, not `HH:MM`. The `_get_today_calendar_context` formatter handles this by using `e['start']` directly, so users see verbose strings like "Saturday, April 26, 2026 at 10:00:00 AM" in the system prompt rather than "10:00". This is functional but verbose.
- **Session save on crash** — the lifespan shutdown handler runs on clean `SIGTERM`/`Ctrl-C` but not on `SIGKILL` or process crash. An unhandled exception that exits the process will lose the session.
- **`REMINDER_LIST` env var name** is read as `APPLE_REMINDER_LIST` (line 23) — this is consistent with the code's own usage but may not match what a user sets if they follow CLAUDE.md which does not specify the exact env var name.

---

## Developer Notes

- The module-level `session` dict is the entire application's persistence layer during a run. Do not add per-request state to it without considering concurrent access (which is not handled).
- When adding new write tool types, update the rollback logic in `confirm_action`. Currently `create_event`, `create_reminder`, and `move_event` have rollback entries; `update_reminder_date` and `delete_event` do not.
- `asyncio.to_thread()` is required for any synchronous blocking call inside an `async def` FastAPI handler. Never call `apple_calendar` or `apple_reminders` functions directly in an async handler without it.
- The `_build_oai_messages()` function fires a live `get_today_events()` AppleScript call on every `/chat` request. This is blocking and will add latency. It is currently called synchronously inside the async handler before the `asyncio.to_thread` call — meaning it blocks the event loop. Consider moving it inside the `run_agent_loop` thread call if latency becomes a problem.
- `pending_state.json` is written next to `app.py` in the project root (`BASE_DIR`). On a fresh checkout without this file, startup is clean. The file is safe to delete manually if the app gets stuck in a confirmation state after a crash.
