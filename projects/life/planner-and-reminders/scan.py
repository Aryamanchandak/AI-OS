import json
import datetime
import apple_calendar
import apple_reminders
from planner import run_agent_loop, build_system_messages

OVERLOAD_THRESHOLD = 4

_SCAN_USER_TEMPLATE = """Run my daily check. Here's the data:

Today: {today}

=== Calendar (next 7 days) ===
{events_text}

=== Open Reminders (all lists) ===
{reminders_text}

=== Pre-analysis (computed by Python — trust these facts, don't redo the date math) ===
{pre_text}

Based on this:
1. Give me a concise morning briefing (2-4 sentences) about what needs attention.
2. If there are missed todos, use update_reminder_date to reschedule them to a realistic future date. Include a new_time (e.g. "09:00") so the alert fires at the right moment.
3. If there are calendar conflicts (overlapping events), use move_event to fix them. Pick a specific non-conflicting slot from the calendar data above — don't guess.
4. Orphaned todos and overloaded days — just mention them in the briefing, no action needed.
5. Don't create new events/reminders to "review" conflicts — use the tools to fix them directly.
6. For move_event, use the exact event title from the calendar data (case-sensitive)."""


def preanalyse(events: list, reminders: list, today_str: str) -> dict:
    """
    Pure Python pre-analysis — no API call.
    Returns missed_todos, orphaned_todos, conflicts, overloaded_days.
    """
    today = datetime.date.fromisoformat(today_str)

    missed_todos = [
        {"title": r["title"], "due": r["due"], "list": r["list"]}
        for r in reminders
        if r["due"] is not None and datetime.date.fromisoformat(r["due"]) < today
    ]

    orphaned_todos = []
    for r in reminders:
        if r["due"] is not None:
            continue
        created = r.get("created")
        if created is None:
            orphaned_todos.append({"title": r["title"], "list": r["list"]})
        else:
            age_days = (today - datetime.date.fromisoformat(created)).days
            if age_days >= 7:
                orphaned_todos.append({"title": r["title"], "list": r["list"], "age_days": age_days})

    timed = [e for e in events if not e.get("allday")]

    # Group timed events by date, then check every pair on the same day
    day_map: dict[str, list] = {}
    for e in timed:
        day_map.setdefault(e["date"], []).append(e)

    conflicts = []
    for day_events in day_map.values():
        sorted_evts = sorted(day_events, key=lambda e: e["start"])
        for i in range(len(sorted_evts)):
            for j in range(i + 1, len(sorted_evts)):
                a = sorted_evts[i]
                b = sorted_evts[j]
                # a starts before b ends AND b starts before a ends → overlap
                if a["start"] < b["end"] and b["start"] < a["end"]:
                    conflicts.append({"a": a, "b": b})

    day_counts: dict[str, int] = {}
    for e in events:
        day_counts[e["date"]] = day_counts.get(e["date"], 0) + 1
    overloaded_days = [
        {"date": d, "count": c}
        for d, c in day_counts.items()
        if c > OVERLOAD_THRESHOLD
    ]

    return {
        "missed_todos": missed_todos,
        "orphaned_todos": orphaned_todos,
        "conflicts": conflicts,
        "overloaded_days": overloaded_days,
    }


def run_daily_scan(calendar_name: str, reminder_list: str, memory_context: str) -> dict:
    """
    Full daily scan pipeline using the agent loop.
    Returns same shape as run_agent_loop: {reply, pending_actions, assistant_msg}.
    """
    today = datetime.date.today().isoformat()

    try:
        events = apple_calendar.get_week_events(calendar_name)
    except Exception as e:
        events = []
        _calendar_error = str(e)
    else:
        _calendar_error = None

    try:
        reminders = apple_reminders.list_all_open_reminders()
    except Exception as e:
        reminders = []
        _reminders_error = str(e)
    else:
        _reminders_error = None

    if not events and not reminders:
        note = ""
        if _calendar_error:
            note += f" (calendar read failed: {_calendar_error})"
        if _reminders_error:
            note += f" (reminders read failed: {_reminders_error})"
        return {
            "reply": f"Nothing found on your calendar or reminders for the next 7 days.{note}",
            "pending_actions": [],
            "assistant_msg": None,
        }

    pre = preanalyse(events, reminders, today)
    events_text = json.dumps(events, indent=2) if events else "[]"
    reminders_text = json.dumps(reminders, indent=2) if reminders else "[]"
    pre_text = json.dumps(pre, indent=2)

    user_content = _SCAN_USER_TEMPLATE.format(
        today=today,
        events_text=events_text,
        reminders_text=reminders_text,
        pre_text=pre_text,
    )

    # Build messages with system prompt + scan user message
    system_msgs = build_system_messages(today, memory_context)
    oai_messages = system_msgs + [{"role": "user", "content": user_content}]

    return run_agent_loop(oai_messages, calendar_name, reminder_list)