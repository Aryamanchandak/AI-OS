# apple_calendar.py — Technical Documentation

**Last updated:** 2026-04-24
**Lines of code:** 249
**Language:** Python (macOS-only, requires `pyobjc-framework-Cocoa`)

---

## What This File Does (Plain English)

This module is the entire interface between the Python application and Apple Calendar. Every calendar operation — creating timed or all-day events, moving events, deleting events, and reading events for today or the coming week — is implemented here as an AppleScript string assembled in Python and executed via macOS's `NSTask` / `osascript`. No `.applescript` files on disk: all scripts are generated inline as Python f-strings.

---

## How It Actually Works

### Entry Points

No main block. This module is imported by `app.py` and `scan.py`. Its public functions are called directly:
- `execute_tool()` in `planner.py` calls `create_timed_event`, `create_allday_event`, `move_event`, `delete_event`, `get_today_events`, and `get_week_events`.
- `app.py` calls `get_today_events` (for ambient context injection) and imports `delete_event` and `move_event` directly for rollback in `confirm_action`.
- `scan.py` calls `get_week_events`.

### Data Flow

**Writes (`create_timed_event`, `create_allday_event`, `move_event`, `delete_event`):**
1. Python receives structured arguments (title, date string, time string, etc.).
2. Arguments are escaped for AppleScript (double-quote escaping only via `.replace('"', '\\"')`).
3. A complete AppleScript program is assembled as an f-string, calling `_date_setter()` inline to build the date manipulation snippet.
4. `_run_applescript()` sends the script to `/usr/bin/osascript` via stdin, using `NSTask`.
5. On non-zero exit code, `RuntimeError` is raised with the stderr content.
6. No return value — success is silence, failure is an exception.

**Reads (`get_week_events`, `get_today_events`):**
1. A date range is computed in Python.
2. AppleScript iterates calendar events within that range and builds a tab-delimited text block, one event per line.
3. `_run_applescript()` returns the raw string from stdout.
4. Python splits on newlines, then on `\t`, into list-of-dicts.
5. On `RuntimeError` from `_run_applescript()`, returns an empty list (silent fallback).

**`move_event` specifically:**
1. Searches for an event by title within the original date's day boundary (midnight to midnight+86399s).
2. If no event with matching title is found on that day, the AppleScript raises an error which becomes a `RuntimeError` in Python.
3. If found, updates `start date` and `end date` in place on the existing event object.

### State Management

This module is stateless. No module-level variables are mutated. Every call is independent.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `_run_applescript(script)` | Runs an AppleScript string via `NSTask` (not `subprocess`). Blocks the calling thread until the script completes. Raises `RuntimeError` if exit code is non-zero, using stderr as the error message (falls back to stdout, then a generic string). |
| `_date_setter(date_str, time_str)` | Returns a multi-line AppleScript snippet that assigns a `date` object to the variable `d`. Accepts `YYYY-MM-DD` and `HH:MM` (24h). Defaults time to `"09:00"` if not supplied. |
| `create_timed_event(summary, date_str, start_time, duration_minutes, description, calendar_name)` | Assembles and runs AppleScript that creates a calendar event with explicit start time and computed end time (`start + duration_minutes * minutes`). No return value. |
| `create_allday_event(summary, date_str, description, calendar_name)` | Creates an all-day event by setting `allday event: true` and making end date = start date + 1 day. No return value. |
| `move_event(original_title, original_date, original_start, new_date, new_start, duration_minutes, calendar_name)` | Finds an existing event by title on the original date, then overwrites its start/end dates. Does not read the original duration from Calendar — uses the `duration_minutes` parameter passed by the caller. |
| `delete_event(title, date_str, calendar_name)` | Finds the first event matching `title` on `date_str` and deletes it. Used by `app.py` for rollback of `create_event` actions. |
| `get_week_events(calendar_name)` | Returns events for the next 7 days as a list of dicts: `{"title", "date": "YYYY-MM-DD", "start": "HH:MM", "end": "HH:MM", "allday": bool}`. Returns `[]` on AppleScript failure. |
| `get_today_events(calendar_name)` | Returns today's events as a list of `{"title": str, "start": str}` dicts. `start` is a raw AppleScript date string (e.g. `"Saturday, 26 April 2026 at 10:00:00 AM"`), not a structured `HH:MM`. Returns `[]` on failure. |

### External Dependencies

- **`Foundation`** (`NSTask`, `NSPipe`, `NSData`) — from `pyobjc-framework-Cocoa`. This makes the module macOS-only and requires PyObjC to be installed. Import fails on Linux.
- **`/usr/bin/osascript`** — the macOS AppleScript interpreter, launched as a subprocess via NSTask.
- **Apple Calendar** — the AppleScript target. Requires Automation permission granted to the Python process in System Settings → Privacy & Security → Automation.
- **`datetime`** from the standard library.

### Error Handling

| Failure | Handling |
|---|---|
| AppleScript exit code non-zero | `_run_applescript()` raises `RuntimeError` with stderr (or stdout if stderr empty) |
| `get_week_events` AppleScript fails | `RuntimeError` caught inside the function, returns `[]` silently |
| `get_today_events` AppleScript fails | `RuntimeError` caught inside the function, returns `[]` silently |
| `create_timed_event`, `create_allday_event`, `delete_event` fail | `RuntimeError` propagates to caller — `execute_tool()` in `planner.py` propagates to `app.py` |
| `move_event` — event not found | AppleScript `error` statement fires → `RuntimeError` propagates to caller |

---

## Non-Technical Decisions Embedded in the Code

- **`NSTask` instead of `subprocess`** — deliberate choice to avoid `fork()` on macOS, which crashes when combined with the OpenAI SDK's use of threading. `NSTask` uses `posix_spawn` instead. This couples the entire module to PyObjC.
- **`get_week_events` uses `__import__('datetime')` inline** for `timedelta` even though `datetime` is already imported at the top of the file. This is a code smell suggesting the function was written or edited in isolation.
- **Tab delimiter (`\t`) in AppleScript output** — the AppleScript uses `tab` to delimit fields within a line, `"\n"` to separate events. Python parses with `split("\t")`. If an event title contains a literal tab character, the parsed output will be silently wrong.
- **`get_today_events` returns `start` as a raw AppleScript date string** — not normalized to `"HH:MM"`. This is inconsistent with `get_week_events` which parses `start` into `"HH:MM"` format. `_get_today_calendar_context()` in `app.py` uses `e['start']` directly, so the system prompt sees verbose date strings rather than times.
- **`create_allday_event` sets end date to `eventDate + (1 * days)`** — matches Apple Calendar's convention where the end date of an all-day event is exclusive (midnight of the next day).
- **`move_event` searches a 86399-second window** (`dayEnd = dayStart + 86399`) to avoid boundary collisions. This misses events starting at exactly `23:59:01` onwards, but such edge cases are unlikely in practice.
- **`_date_setter` defaults to `"09:00"`** — if `time_str` is omitted, the date is set to 9 AM, not midnight. This affects `create_timed_event` behavior when called without an explicit time.
- **No retry logic** anywhere in this file.
- **`calendar_name` is always passed in as a parameter** — the module does not read env vars itself; callers (`app.py` via `execute_tool`, `scan.py`) read `APPLE_CALENDAR_NAME` from the environment and pass it down.
- **Every write function calls `Calendar.launch`** in its AppleScript — this will bring Calendar.app to the foreground on the user's screen.

---

## Honest Gaps and Risks

- **Event titles with tab characters will silently corrupt parsed output** in `get_week_events` and `get_today_events` — the tab splits into extra fields and the event dict will be malformed or dropped.
- **`move_event` finds the event by title only, within the original date's day** — if two events share the same title on the same day, it moves the first one the AppleScript iterator encounters. The sort order is not guaranteed.
- **`move_event` does not preserve the original event duration** — it requires `duration_minutes` from the caller. `app.py`'s rollback passes the original args back, so the rollback move uses the same duration. But if the original event had a duration that was never stored, the caller defaults to 60 minutes.
- **`delete_event` only deletes the first matching event on the given date** — same limitation as `move_event`'s search.
- **`get_today_events` `start` field is not normalized** — downstream callers that expect `HH:MM` format (e.g. for display or comparison) will get the wrong string.
- **No permissions check before writing** — if Automation permission is not granted, the AppleScript will fail with a permissions error surfaced as a `RuntimeError`. The error message will be an AppleScript error string, not a guided instruction for the user.
- **`_run_applescript` blocks the calling thread** — for reads with many events, this is slow. Currently safe because `scan.py` runs via `asyncio.to_thread`, and `app.py` calls `get_today_events` synchronously inside `_build_oai_messages` before the thread dispatch. That synchronous call blocks the event loop — a latency risk if the calendar read is slow.

---

## Developer Notes

- Every function that assembles an AppleScript f-string must escape user-provided strings with `.replace('"', '\\"')` before interpolating them. Currently `summary`, `description`, and `original_title` are escaped in their respective functions. `calendar_name` is interpolated unescaped — a calendar name containing a double-quote would break the generated script.
- To test any function in isolation: `from apple_calendar import create_timed_event; create_timed_event("Test", "2026-04-27", "10:00", 30, "", "Calendar")` — this creates a real event. Use a throwaway calendar for testing.
- The `Foundation` import will fail outside macOS or without PyObjC. Any CI that runs on Linux will need to mock this module entirely.
- If you need to switch from `NSTask` back to `subprocess`, note the CLAUDE.md warning: `subprocess.run(['osascript', ...])` uses `fork()` which crashes the OpenAI SDK on macOS. Do not use `subprocess` unless you are certain no OpenAI API calls are in flight on other threads.
- `_run_applescript` in this file and in `apple_reminders.py` are identical implementations. Any bug fix must be applied to both. Consider extracting to a shared `applescript_runner.py` module if the codebase grows.
