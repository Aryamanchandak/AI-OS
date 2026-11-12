# scan.py — Technical Documentation

**Last updated:** 2026-04-24
**Lines of code:** 142
**Language:** Python

---

## What This File Does (Plain English)

This module implements the daily scan pipeline. It reads all Apple Calendar events for the next 7 days and all open reminders across every Reminders list, runs pure Python pre-analysis to identify missed todos, calendar conflicts, orphaned todos, and overloaded days, then sends all of this data to the LLM via the same `run_agent_loop` used by the normal chat flow. The model produces a morning briefing and can propose write actions (rescheduling reminders, moving conflicting events) through the same tool-calling mechanism. The result is returned to `app.py` in the same `{reply, pending_actions, assistant_msg}` shape as a normal chat turn.

---

## How It Actually Works

### Entry Points

One public function: `run_daily_scan(calendar_name, reminder_list, memory_context)`. Called from `app.py`'s `POST /daily` handler via `asyncio.to_thread()` because its Apple API calls are blocking.

### Data Flow

1. **Read calendar** — `apple_calendar.get_week_events(calendar_name)`. On failure, `events = []` and `_calendar_error` is set to the error string.
2. **Read reminders** — `apple_reminders.list_all_open_reminders()`. On failure, `reminders = []` and `_reminders_error` is set.
3. **Early exit** — if both are empty, return a plain text result with any error notes appended.
4. **Pre-analysis** — `preanalyse(events, reminders, today_str)` computes four lists using pure Python: `missed_todos`, `orphaned_todos`, `conflicts`, `overloaded_days`. No API call.
5. **Assemble user message** — formats `_SCAN_USER_TEMPLATE` with today's date, raw events JSON, raw reminders JSON, and pre-analysis JSON.
6. **Build system messages** — calls `build_system_messages(today, memory_context)` from `planner.py` (same system prompt as the chat flow; no calendar context injected since the calendar data is already in the user message).
7. **Run agent loop** — calls `run_agent_loop(oai_messages, calendar_name, reminder_list)` from `planner.py`.
8. Returns the loop result directly — same `{reply, pending_actions, assistant_msg}` shape.

### preanalyse — What It Computes

`preanalyse(events, reminders, today_str)` is a pure function (no API calls, no side effects):

- **`missed_todos`** — reminders where `due` is not `None` and `due < today`. Shape: `[{"title", "due", "list"}]`.
- **`orphaned_todos`** — reminders where `due is None`. If `created` is also `None`, added unconditionally. If `created` is set, only added if `age_days >= 7`. Shape: `[{"title", "list"}]` or `[{"title", "list", "age_days"}]`.
- **`conflicts`** — pairs of timed events on the same day whose time ranges overlap. Uses string comparison on `"HH:MM"` times (lexicographic, safe for zero-padded 24h format). Checks all O(n²) pairs per day (not just adjacent). Shape: `[{"a": event_dict, "b": event_dict}]`.
- **`overloaded_days`** — days where total event count (including all-day events) exceeds `OVERLOAD_THRESHOLD` (4). Shape: `[{"date", "count"}]`.

### State Management

Module-level constants:
- `OVERLOAD_THRESHOLD = 4` — events per day before flagging as overloaded.
- `_SCAN_USER_TEMPLATE` — the structured prompt template injected as a user message to the agent loop.

No mutable state.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `preanalyse(events, reminders, today_str)` | Pure Python. Returns a dict with four lists: `missed_todos`, `orphaned_todos`, `conflicts`, `overloaded_days`. No API call, no side effects. |
| `run_daily_scan(calendar_name, reminder_list, memory_context)` | Full pipeline: reads calendar and reminders, pre-analyses, builds messages, delegates to `run_agent_loop`. Returns `{reply, pending_actions, assistant_msg}`. |

### External Dependencies

- **`apple_calendar.get_week_events(calendar_name)`** — blocking AppleScript call.
- **`apple_reminders.list_all_open_reminders()`** — blocking AppleScript call that reads across all Reminders lists.
- **`planner.run_agent_loop`** — the agent loop. The scan does not call OpenAI directly; it delegates entirely.
- **`planner.build_system_messages`** — for the system prompt.
- **Standard library:** `json`, `datetime`.
- **No `os`, no model, no OpenAI client** — scan.py does not make any OpenAI calls itself.

### Error Handling

| Failure | Handling |
|---|---|
| `get_week_events()` raises | Caught, `events = []`, error string in `_calendar_error` |
| `list_all_open_reminders()` raises | Caught, `reminders = []`, error string in `_reminders_error` |
| Both empty after errors | Returns early with plain text result noting which reads failed |
| `run_agent_loop()` raises | Not caught — propagates to `app.py`'s `asyncio.to_thread` wrapper, which catches `Exception` and returns an error result |

---

## Non-Technical Decisions Embedded in the Code

- **Pre-analysis sends both raw data AND pre-computed analysis to the LLM** — the `_SCAN_USER_TEMPLATE` explicitly tells the model not to redo date arithmetic. This is a good separation: Python does objective computation (what is overdue, what overlaps), the LLM does judgment and language (what to say about it, which actions to take).
- **Conflict detection checks all O(n²) pairs per day** — unlike the old implementation which only checked adjacent events, the current `preanalyse` uses a nested loop over `range(i+1, len(sorted_evts))`. This finds all overlapping pairs, including non-adjacent ones.
- **Conflict detection uses string comparison on `"HH:MM"` times** — `a["start"] < b["end"]` compares strings lexicographically. This is correct for zero-padded 24-hour format as produced by `get_week_events`. All-day events are excluded from conflict detection (`timed = [e for e in events if not e.get("allday")]`).
- **Overload threshold counts all events including all-day events** — `day_counts` is built from all `events` without filtering. A day with 3 birthday reminders (all-day) plus 2 real meetings counts as 5 events and is flagged as overloaded. This is inconsistent with conflict detection, which excludes all-day events.
- **`OVERLOAD_THRESHOLD = 4` is not configurable** — hardcoded module-level constant. Not in env, not in config.
- **Memory context is passed in from `app.py`** — `run_daily_scan` receives `memory_context` as a parameter. This means the daily scan uses the same memory context as the chat flow. The morning briefing may reference past sessions.
- **No calendar context injected into the system prompt** — `build_system_messages(today, memory_context)` is called without a `calendar_context` argument, so the `_SYSTEM` prompt's `{calendar_context}` placeholder is empty. The calendar data is instead included in the user message body via `_SCAN_USER_TEMPLATE`. This avoids duplication.
- **`_calendar_error` and `_reminders_error` are always defined** — the `try/except/else` pattern (`_calendar_error = str(e)` in except, `_calendar_error = None` in else) guarantees both are defined in all branches. The empty-check block below can safely reference them. This is correct but requires careful reading.

---

## Honest Gaps and Risks

- **Orphaned todo detection is only partially effective when `created` is `None`** — if `list_all_open_reminders` cannot read the creation date for a reminder, `created` is `None` and the item is flagged as orphaned immediately (regardless of how recently it was created). New items without a creation date look the same as very old ones.
- **Overload counting includes all-day events** — flagging a day as overloaded because of 4 birthdays is misleading. Conflict detection and overload detection treat all-day events inconsistently.
- **`preanalyse` conflict detection catches all pairs within a day** — this is an improvement over adjacent-only checking, but the overlap condition `a["start"] < b["end"] and b["start"] < a["end"]` relies on `"HH:MM"` string comparison. If `get_week_events` ever returns a start or end that is not zero-padded, the comparison may give wrong results.
- **`run_agent_loop` may propose write actions in the scan result** — the model can call `move_event` or `update_reminder_date` during the daily scan. These are paused for confirmation in `app.py` via the same pending actions mechanism as regular chat. This is intentional, but the scan system prompt must keep the model focused enough not to propose spurious writes based on the raw data.
- **The model is instructed to use exact event titles (case-sensitive)** — the scan user template says "use the exact event title from the calendar data". If the model alters casing or truncates a long title, `move_event` in `apple_calendar.py` will raise "Event not found". The instruction is enforced only by prompt; model compliance is not guaranteed.
- **No timeout on `run_agent_loop`** — the daily scan can include a large amount of data (full week of events + all reminders + pre-analysis). If the agent loop runs multiple iterations (read tool auto-execution + a write proposal), the total time before a response could be substantial. `app.py` wraps it in `asyncio.to_thread` with no timeout.
- **Early exit message is not surfaced conversationally** — if both calendar and reminders return empty (due to errors or genuinely nothing), the function returns a plain string `"Nothing found on your calendar or reminders for the next 7 days."` with any error notes appended. This is functional but not as polished as the LLM-generated briefings.

---

## Developer Notes

- `run_daily_scan` must always be called via `asyncio.to_thread()` from async contexts. Its `get_week_events` and `list_all_open_reminders` calls are blocking (NSTask AppleScript). `app.py` does this correctly.
- `preanalyse` has no side effects and no API calls — it is the safest function to unit test in the module. Construct synthetic `events` and `reminders` lists matching the shapes returned by `get_week_events` and `list_all_open_reminders`.
- The scan's system prompt is `_SYSTEM` from `planner.py` (shared with the chat flow), plus the scan user message. The model's behaviour in the daily scan is governed by the same behavioural rules as regular chat, with the scan data provided as the user turn. If you want scan-specific model behaviour, you would need a scan-specific system prompt or a prefix in the user message.
- The `_SCAN_USER_TEMPLATE` has numbered instructions (1–6) that directly shape the model's scan output. If adding a new scan category (e.g. "events with no description"), add a numbered instruction here and add the corresponding pre-analysis to `preanalyse`.
- When testing: the pre-analysis runs before any LLM call. Add a `print(json.dumps(pre, indent=2))` after the `preanalyse` call to inspect what the model receives before committing to a full scan run.
