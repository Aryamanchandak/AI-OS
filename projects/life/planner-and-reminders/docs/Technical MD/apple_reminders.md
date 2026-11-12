# apple_reminders.py — Technical Documentation

**Last updated:** 2026-04-24
**Lines of code:** 251
**Language:** Python (macOS-only, requires `pyobjc-framework-Cocoa`)

---

## What This File Does (Plain English)

This module owns every interaction with Apple Reminders. It can create reminder lists, add reminders with due dates and optional alert times, list open reminders from a specific list or from all lists across the app, update a reminder's due date by matching on title, bulk-delete a list's contents, mark a reminder as complete, and delete a specific reminder by title. All operations are performed by generating AppleScript strings in Python and executing them via `NSTask`.

---

## How It Actually Works

### Entry Points

No main block. Imported by `app.py` and `planner.py`. Functions are called directly:
- `execute_tool()` in `planner.py` calls `ensure_list`, `create_reminder`, `list_open_reminders`, `list_all_open_reminders`, `update_reminder_date`.
- `app.py` imports `ensure_list` (called at the start of `confirm_action`) and `delete_reminder` (for rollback).
- `scan.py` calls `list_all_open_reminders`.

### Data Flow

**Writes (`ensure_list`, `create_reminder`, `update_reminder_date`, `delete_reminder`, `clear_list`, `complete_reminder`):**
1. Python receives arguments, escapes double-quotes for AppleScript (`.replace('"', '\\"')`).
2. An AppleScript program is assembled as an f-string, using `_date_setter()` for date handling.
3. `_run_applescript()` executes it via `NSTask`.
4. Success is silence; failure raises `RuntimeError`.

**Reads (`list_open_reminders`, `list_all_open_reminders`):**
1. AppleScript iterates reminders, builds a tab-delimited text block.
2. `_run_applescript()` returns the raw stdout string.
3. Python splits on newlines, then on `\t`, into list-of-dicts.
4. On `RuntimeError`, returns `[]` silently.

### State Management

Stateless. No module-level mutable state.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `_run_applescript(script)` | Identical implementation to `apple_calendar._run_applescript` — runs script via `NSTask`, raises `RuntimeError` on non-zero exit. |
| `_date_setter(date_str, time_str)` | Returns AppleScript snippet setting `d` to the given date and time. Defaults to `"00:00"` if `time_str` is empty. Unlike the calendar version which defaults to `"09:00"`, this version defaults to midnight. |
| `ensure_list(list_name)` | Idempotent: creates the Reminders list if it does not exist, otherwise does nothing. |
| `create_reminder(title, notes, due_date_str, list_name, due_time_str)` | Creates a reminder with a due date and optional alert time. If `due_time_str` is empty, the due date is midnight. Sets both `due date` and `remind me date` to the same value so the alert fires at the specified time. |
| `list_open_reminders(list_name)` | Returns `[{"title": str, "due": str}]` for non-completed reminders in a specific list. `due` is a raw AppleScript date string (e.g. `"Saturday, 26 April 2026 at 00:00:00"`), not normalized. |
| `list_all_open_reminders()` | Returns `[{"title", "due", "list", "created"}]` across all Reminders lists. `due` is `"YYYY-MM-DD"` or `None`. `created` is `"YYYY-MM-DD"` or `None`. |
| `update_reminder_date(title, list_name, new_date_str, new_time_str)` | Finds an open reminder by exact title match in the given list, sets its `due date` and `remind me date`. Raises `RuntimeError` (via AppleScript error) if no match is found. |
| `delete_reminder(title, list_name)` | Deletes the first open reminder matching the title in the given list. Silently does nothing if no match is found. Used by `app.py` for rollback of `create_reminder` actions. |
| `clear_list(list_name)` | Deletes ALL reminders in the list. If the list does not exist, creates it empty instead. Destructive with no undo. |
| `complete_reminder(title, list_name)` | Sets `completed = true` on the first open reminder matching the title. Silently does nothing if no match found. Currently has no caller in the application. |

### External Dependencies

- **`Foundation`** (`NSTask`, `NSPipe`, `NSData`) — from `pyobjc-framework-Cocoa`. macOS-only.
- **`/usr/bin/osascript`** — the AppleScript interpreter.
- **Apple Reminders** — requires Automation permission in System Settings → Privacy & Security → Automation.
- **`datetime`** from the standard library.

### Error Handling

| Failure | Handling |
|---|---|
| AppleScript non-zero exit | `RuntimeError` raised by `_run_applescript()` |
| `list_open_reminders` AppleScript fails | `RuntimeError` caught inside the function, returns `[]` |
| `list_all_open_reminders` AppleScript fails | `RuntimeError` caught inside the function, returns `[]` |
| `update_reminder_date` — no match | AppleScript `error` statement fires → `RuntimeError` propagates to caller |
| `ensure_list`, `create_reminder`, `delete_reminder`, `clear_list`, `complete_reminder` fail | `RuntimeError` propagates to caller |

---

## Non-Technical Decisions Embedded in the Code

- **`create_reminder` accepts a `due_time_str` parameter** — when provided, this sets both `due date` and `remind me date` to that specific time, causing Apple Reminders to fire a notification at that moment. When omitted, the reminder lands at midnight and alerts at midnight (effectively the start of the day).
- **`list_open_reminders` returns `due` as a raw AppleScript date string** (e.g. `"Saturday, 26 April 2026 at 00:00:00"`) while `list_all_open_reminders` normalizes to `"YYYY-MM-DD"`. These two functions return inconsistently shaped dicts using the same key name `"due"`.
- **Tab delimiter (`\t`) in AppleScript output** — fields are separated by `tab`, entries by `"\n"`. Python parses with `split("\t")`. A reminder title or notes containing a literal tab will silently corrupt the parsed output.
- **`list_all_open_reminders` does populate `created`** — the AppleScript reads `creation date of r` via a `try/on error` block and formats it as `"YYYY-MM-DD"`. If reading creation date fails (some older Reminders entries may not have this property), it falls back to `"none"` which becomes `None` in Python.
- **`update_reminder_date` matches by exact title** — if two open reminders share the same title in the same list, only the first match (in AppleScript's undefined iteration order) is updated.
- **`clear_list` is destructive with no confirmation or undo** — it deletes every reminder in the list. It is not currently called from `app.py` or `scan.py` in the active code paths. It was previously used by a daily scan to refresh a "Today" list but that code path has been removed.
- **`complete_reminder` silently does nothing if no match is found** — no error, no return value. The caller cannot distinguish "completed successfully" from "nothing matched".
- **`_run_applescript` is copy-pasted from `apple_calendar.py`** — the two implementations are identical. Any bug fix must be applied to both files.
- **`NSTask` is used instead of `subprocess`** — same rationale as `apple_calendar.py`: avoids `fork()` crash with the OpenAI SDK on macOS.
- **`ensure_list` must be called before `create_reminder`** for any list that might not exist. `app.py` calls `ensure_list(REMINDER_LIST)` once at the top of `confirm_action`. `execute_tool` in `planner.py` also calls `ensure_list` before `create_reminder`.

---

## Honest Gaps and Risks

- **Reminder titles with tab characters will silently corrupt parsed output** in both list functions — same fragility as `apple_calendar.py`.
- **`list_open_reminders` and `list_all_open_reminders` return different `due` formats** — `list_open_reminders` returns a verbose date string, `list_all_open_reminders` returns `"YYYY-MM-DD"` or `None`. Code that uses both functions and treats `due` the same way will behave differently. `scan.py` uses `list_all_open_reminders` (normalized). `execute_tool` in `planner.py` uses `list_open_reminders` when a specific list is given.
- **Reminder title matching is the only identifier** — there are no IDs. If a title is edited in Apple Reminders between when the scan runs and when the user confirms a reshuffle, `update_reminder_date` will raise `RuntimeError` (no match found).
- **`complete_reminder` is defined but never called from any active code path** — it is either dead code or planned for a feature not yet implemented.
- **`clear_list` creates the list if it does not exist** — calling `clear_list("Some List")` on a list that does not exist leaves an empty list behind, which may be unexpected.
- **Newlines within a reminder title or body break the tab-delimited output format** — the AppleScript does not escape or quote values before concatenating them.
- **`created` date fallback is `"none"` → `None`** — the AppleScript uses a `try/on error` block when reading `creation date`. If the creation date is unavailable for any reminder (possible for very old items or Reminders synced from iCloud with incomplete metadata), `created` will be `None` for that item. `scan.py`'s `preanalyse` correctly handles this by treating `created is None` reminders as orphaned if they also have no due date.

---

## Developer Notes

- `ensure_list()` must always be called before `create_reminder()` for a given list name. `execute_tool()` in `planner.py` calls it immediately before `create_reminder`. If you add a new code path that calls `create_reminder()` for a different list, ensure `ensure_list()` is called first.
- `clear_list()` creates the list if it does not exist — different from `ensure_list()` which is purely a check-and-create without deleting contents.
- The `_run_applescript` function here and in `apple_calendar.py` are identical. If you fix a bug in one, fix it in the other. Consider extracting to a shared `applescript_runner.py` if the codebase grows.
- To test in isolation without affecting real data: create a throwaway Reminders list (e.g. "Test List"), call `ensure_list("Test List")`, `create_reminder("Test", "", "2026-05-01", "Test List", "09:00")`, `list_open_reminders("Test List")`, then `clear_list("Test List")`.
- `delete_reminder` is used exclusively for rollback in `app.py`'s `confirm_action`. It deletes the first open matching reminder — if the create succeeded and created two items (should not happen but defensive concern), only one is rolled back.
