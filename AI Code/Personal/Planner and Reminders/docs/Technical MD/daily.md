# daily.py — Technical Documentation

**Last updated:** 2026-04-11
**Lines of code:** 87
**Language:** Python

---

## What This File Does (Plain English)

This module implements the "daily briefing" feature — a distinct, simpler alternative to the full daily scan in `scan.py`. It reads today's Apple Calendar events and open reminders from the `REMINDER_LIST` (a single named list, not all lists), asks the LLM to produce a prioritized to-do list, writes that list to a separate "Today" Reminders list, and returns a formatted markdown string for display in chat. It has no mode-switching or plan JSON output — it is a one-shot read-and-summarize operation.

---

## How It Actually Works

### Entry Points

One public function: `generate_daily_briefing()`. It is not currently called from `app.py`. The `app.py` `/daily` endpoint calls `run_daily_scan()` from `scan.py` instead. `daily.py` appears to be an earlier or parallel implementation.

### Data Flow

1. Get today's date.
2. Call `apple_calendar.get_today_events(CALENDAR_NAME)` — returns list of `{"title", "start"}` where `start` is a raw AppleScript date string.
3. Call `apple_reminders.list_open_reminders(REMINDER_LIST)` — returns list of `{"title", "due"}` where `due` is a raw AppleScript date string.
4. If both are empty, return an early "nothing today" message immediately.
5. Format events and tasks as plain text blocks.
6. Send to LLM (GPT via `_client.chat.completions.create`) with a prompt requesting a JSON response: `{"items": [{"title", "priority", "source"}]}`.
7. Parse the JSON response. Fallback: if parsing fails or the response is not a list, `items = []`.
8. Call `apple_reminders.ensure_list("Today")` then `apple_reminders.clear_list("Today")` — wipes the "Today" list completely.
9. For each item with a non-empty title, call `apple_reminders.create_reminder(title, "", today_iso, "Today")`.
10. Build a formatted markdown string with emoji priority indicators and return it.

### State Management

Stateless. No module-level mutable state. `_client` and `_model` are module-level constants initialized once at import time.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `generate_daily_briefing()` | The only function. Reads today's events and open tasks, calls LLM, writes prioritized list to "Today" Reminders list, returns formatted markdown string. |

### External Dependencies

- **`apple_calendar.get_today_events(CALENDAR_NAME)`** — reads today's events.
- **`apple_reminders.list_open_reminders(REMINDER_LIST)`** — reads open reminders from the work tracker list.
- **`apple_reminders.ensure_list("Today")`**, **`apple_reminders.clear_list("Today")`**, **`apple_reminders.create_reminder(...)`** — writes to the "Today" list.
- **OpenAI API** — `chat.completions.create` with `response_format={"type": "json_object"}`.
- **Environment variables:** `OPENAI_API_KEY`, `APPLE_CALENDAR_NAME` (default `"Calendar"`), `APPLE_REMINDER_LIST` (default `"Work Tracker"`).
- **`_model = "gpt-5.4-nano"`** — this model name is invalid as of the knowledge cutoff. This call will fail at runtime.

---

## Non-Technical Decisions Embedded in the Code

- **Reads only `REMINDER_LIST` (one list)** — unlike `scan.py` which calls `list_all_open_reminders()`, this function only reads the configured work tracker list. If the user has tasks in other lists, they are invisible here.
- **"Today" list is wiped on every call** — `clear_list("Today")` is called unconditionally. Any manually added items in the "Today" list are destroyed.
- **JSON fallback is silent** — if the LLM returns invalid JSON or a dict without `"items"` or `"tasks"` keys, `items = []` and the "Today" list is cleared but not repopulated. No error is surfaced.
- **`items.get("items", items.get("tasks", []))`** — the code handles two possible JSON root keys (`"items"` or `"tasks"`) as a defensive fallback. This implies the prompt or model was inconsistent at some point during development.
- **Emoji in output** — `priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}` — the only file in the codebase that writes emoji to its output.
- **`response_format={"type": "json_object"}`** is used — this forces the model to return valid JSON, but the code still wraps the parse in a `try/except`, suggesting past failures even with structured output.
- **`today_iso` for reminder due dates** — all items from the LLM are given today's date as their due date in the "Today" list, regardless of their actual urgency or calendar position.

---

## Honest Gaps and Risks

- **`_model = "gpt-5.4-nano"` is an invalid model name** — the API call in `generate_daily_briefing()` will fail with an API error at runtime.
- **`generate_daily_briefing()` is not called from `app.py`** — the `/daily` endpoint in `app.py` calls `scan.run_daily_scan()` instead. This entire module may be unreachable from the current UI. It is unclear whether it is intentionally kept as an alternative or is simply dead code.
- **Silent empty output on JSON parse failure** — if `items = []`, the "Today" list is cleared and nothing is written. The returned string will just say "Your to-do for [date]:" followed by the sync count line `"_0 items synced to your 'Today' Reminders list._"`. The user has no indication that an error occurred.
- **`get_today_events` returns `start` as a raw AppleScript date string** — the LLM prompt will contain something like `"at Saturday, 11 April 2026 at 10:00:00 AM"` instead of `"10:00"`. The LLM can generally parse this but it is noisy and inconsistent with `scan.py`'s approach.
- **`clear_list` destructive wipe** — if the user runs the daily briefing twice in a row, all manually added "Today" items are deleted both times. No warning is given.
- **No error propagation** — if any Apple API call raises `RuntimeError` (permissions denied, script failure), it propagates unhandled out of `generate_daily_briefing()`. The caller must catch it. In the current codebase, there is no caller in `app.py`, so this is moot but risky if wired in.

---

## Developer Notes

- This module is likely a predecessor to the more complete `scan.py` flow. Before adding features here, check whether `scan.py`'s `run_daily_scan()` already handles the same use case more completely.
- If you want to wire `generate_daily_briefing()` into `app.py`, add a try/except around the call and handle the case where `items = []` (show a friendly error rather than a blank list).
- The "Today" list name is hardcoded as the string `"Today"` at the top of the module. If the user has a differently named list they want to use, this requires a code change — it is not configurable via env var.
- Fix the model name before testing: change `"gpt-5.4-nano"` to `"gpt-4o"` or another valid model ID.
