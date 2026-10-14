import os
import json
import datetime
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from dotenv import load_dotenv

import apple_calendar
import apple_reminders
import upi_tools

load_dotenv()
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_model = "gpt-4o"

# ── System prompt ────────────────────────────────────────────────────────────

_SYSTEM = """You are a smart planning collaborator with direct access to Apple Calendar and Apple Reminders.
Today is {today}. The user is in IST (UTC+5:30).

## Core behaviour
- A "hi" is just a hi. Don't call tools unless the message is schedule-related.
- Before proposing any new event time, ALWAYS call check_calendar first to see what's already there. Never guess at availability.
- If the user's request is ambiguous (no date, no time, no duration), ask ONE targeted question before calling any write tool.
- Nothing is written until the user confirms — you propose, they approve.

## Handling complex / multi-step goals
When someone gives you a complex goal (e.g. "prepare for my investor pitch next Friday", "plan my week", "set up the project kickoff"):
1. Call check_calendar first to understand what space exists.
2. Break the goal into concrete, sequenced sub-tasks. Each sub-task should be a distinct event or reminder, not a vague block.
3. For events: assign specific dates and times based on real calendar availability — not generic placeholders.
4. For reminders: attach a specific due date AND a due time (e.g. 09:00 the day before a deadline) so the alert fires at the right moment.
5. Show the full set of proposed actions together before calling any write tools, so the user can review the whole picture.
6. Ask about dependencies: "Does the prep session need to finish before the pitch, or is there buffer?"

## Reminder quality
- Always include a `time` when creating reminders — use a sensible alert time (e.g. 09:00 for morning tasks, 1 hour before a deadline).
- Put the actual task detail in `description`, not crammed into the title.
- Due date should be the day the action needs to be done, not the day of the downstream event.

## Calendar quality  
- Default meeting duration 60 mins unless context suggests otherwise.
- Prefer existing open slots (not back-to-back with other events).
- If you spot a conflict in the calendar data you retrieved, flag it explicitly.

## Conflict awareness
If check_calendar reveals overlapping events, point this out immediately and offer to move one.

{calendar_context}"""

_MEMORY_BLOCK = """You have memory of past sessions with this user. Use it to:
- Acknowledge relevant context naturally and briefly
- Avoid asking about things you already know
- Reference past commitments or follow-ups if relevant

Keep acknowledgment brief — one sentence max.

--- MEMORY FROM PREVIOUS SESSIONS ---
{memory_context}
--- END MEMORY ---"""

# ── Tool schemas ─────────────────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "check_calendar",
            "description": "Read the user's Apple Calendar events. Use this to see what's on their schedule before proposing new events, or when they ask about their calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days ahead to check. Use 1 for today only, 7 for the week.",
                        "default": 7,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_reminders",
            "description": "Read the user's open Apple Reminders (todos). Returns all incomplete reminders with their due dates and list names.",
            "parameters": {
                "type": "object",
                "properties": {
                    "list_name": {
                        "type": "string",
                        "description": "Optional: filter to a specific reminders list. Omit to get all lists.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Create a new event in Apple Calendar. Use when the user wants to schedule a meeting, block time, or add a calendar event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title"},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                    "time": {"type": "string", "description": "Start time in HH:MM 24h format. Omit for all-day event."},
                    "duration_minutes": {"type": "integer", "description": "Duration in minutes. Default 60.", "default": 60},
                    "description": {"type": "string", "description": "Optional event description", "default": ""},
                },
                "required": ["title", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Create a new reminder (todo) in Apple Reminders. Use when the user wants to remember something, track a task, or set a todo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Reminder title"},
                    "date": {"type": "string", "description": "Due date in YYYY-MM-DD format"},
                    "time": {"type": "string", "description": "Due time in HH:MM 24h format. Always include a sensible time (e.g. 09:00 for morning tasks, or 1 hour before a deadline). This sets the alert time in Apple Reminders."},
                    "description": {"type": "string", "description": "Optional notes — use this for task detail, context, or instructions. Keep the title short.", "default": ""},
                },
                "required": ["title", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_event",
            "description": "Move an existing calendar event to a new date/time. Use to resolve conflicts or reschedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "original_title": {"type": "string", "description": "Exact title of the event to move"},
                    "original_date": {"type": "string", "description": "Current date of the event (YYYY-MM-DD)"},
                    "original_start": {"type": "string", "description": "Current start time (HH:MM)"},
                    "new_date": {"type": "string", "description": "New date (YYYY-MM-DD)"},
                    "new_start": {"type": "string", "description": "New start time (HH:MM)"},
                    "duration_minutes": {"type": "integer", "description": "Duration in minutes. Default 60.", "default": 60},
                },
                "required": ["original_title", "original_date", "original_start", "new_date", "new_start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_reminder_date",
            "description": "Change the due date (and optionally the due time) of an existing reminder. Use to reschedule missed or overdue todos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Exact title of the reminder"},
                    "list_name": {"type": "string", "description": "Name of the reminder list it belongs to"},
                    "new_date": {"type": "string", "description": "New due date (YYYY-MM-DD)"},
                    "new_time": {"type": "string", "description": "New due time in HH:MM 24h format. Include to set a timed alert. If omitted, time stays at midnight."},
                },
                "required": ["title", "list_name", "new_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": "Delete a calendar event. Use when the user wants to cancel or remove an event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Exact title of the event to delete"},
                    "date": {"type": "string", "description": "Date of the event (YYYY-MM-DD)"},
                },
                "required": ["title", "date"],
            },
        },
    },
    # ── UPI / spending tools (read-only, hit local SQLite ledger) ────────────
    {
        "type": "function",
        "function": {
            "name": "upi_spend_today",
            "description": "Total UPI spend (debits) so far today, in INR. Use when the user asks how much they've spent today.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upi_spend_by_category",
            "description": "UPI spend grouped by category (Food, Travel, Bills, etc.) over the last `days` days. If `category` is given, returns only that category's total. Use for questions like 'how much did I spend on food last month?' or 'what's my spending breakdown?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Optional category filter (e.g. 'Food', 'Travel'). Omit for full breakdown."},
                    "days": {"type": "integer", "description": "Lookback window in days. Default 30.", "default": 30},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upi_recent_payments",
            "description": "List the most recent UPI payments (newest first) with amount, direction, counterparty, and any calendar context. Use for 'show my recent payments' or 'what was my last transaction?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "How many payments to return. Default 10, max 100.", "default": 10},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upi_top_recipients",
            "description": "Top counterparties by total UPI debit amount in the window. Use for 'who am I spending the most on?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Lookback window in days. Default 30.", "default": 30},
                    "limit": {"type": "integer", "description": "Max recipients to return. Default 10.", "default": 10},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upi_goals_status",
            "description": "Status of active spending goals (avoid_merchant, budget_cap, frequency_cap) and their progress. Use for 'how am I doing on my budget?' or 'check my spending goals'.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# Tools that are safe to auto-execute (read-only)
_READ_TOOLS = {
    "check_calendar", "check_reminders",
    "upi_spend_today", "upi_spend_by_category",
    "upi_recent_payments", "upi_top_recipients", "upi_goals_status",
}

# Tools that require user confirmation before execution
_WRITE_TOOLS = {"create_event", "create_reminder", "move_event", "update_reminder_date", "delete_event"}


# ── Tool execution ───────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict, calendar_name: str, reminder_list: str) -> str:
    """
    Execute a tool call and return the result as a string.
    Raises RuntimeError on AppleScript failures (caller should handle).
    """
    if name == "check_calendar":
        days = args.get("days_ahead", 7)
        if days <= 1:
            events = apple_calendar.get_today_events(calendar_name)
        else:
            events = apple_calendar.get_week_events(calendar_name)
        if not events:
            return "No events found."
        return json.dumps(events, indent=2)

    elif name == "check_reminders":
        list_name = args.get("list_name")
        if list_name:
            reminders = apple_reminders.list_open_reminders(list_name)
        else:
            reminders = apple_reminders.list_all_open_reminders()
        if not reminders:
            return "No open reminders found."
        return json.dumps(reminders, indent=2)

    elif name == "create_event":
        time_val = args.get("time")
        if time_val:
            apple_calendar.create_timed_event(
                args["title"], args["date"], time_val,
                args.get("duration_minutes", 60),
                args.get("description", ""), calendar_name,
            )
        else:
            apple_calendar.create_allday_event(
                args["title"], args["date"],
                args.get("description", ""), calendar_name,
            )
        return f"Created event: {args['title']} on {args['date']}"

    elif name == "create_reminder":
        apple_reminders.ensure_list(reminder_list)
        apple_reminders.create_reminder(
            args["title"], args.get("description", ""),
            args["date"], reminder_list,
            args.get("time", ""),
        )
        time_str = f" at {args['time']}" if args.get("time") else ""
        return f"Created reminder: {args['title']} due {args['date']}{time_str}"

    elif name == "move_event":
        apple_calendar.move_event(
            args["original_title"], args["original_date"], args["original_start"],
            args["new_date"], args["new_start"],
            args.get("duration_minutes", 60), calendar_name,
        )
        return f"Moved '{args['original_title']}' to {args['new_date']} {args['new_start']}"

    elif name == "update_reminder_date":
        apple_reminders.update_reminder_date(
            args["title"], args["list_name"], args["new_date"],
            args.get("new_time", ""),
        )
        time_str = f" at {args['new_time']}" if args.get("new_time") else ""
        return f"Updated '{args['title']}' due date to {args['new_date']}{time_str}"

    elif name == "delete_event":
        apple_calendar.delete_event(args["title"], args["date"], calendar_name)
        return f"Deleted event: {args['title']} on {args['date']}"

    # ── UPI tools ────────────────────────────────────────────────────────────
    elif name == "upi_spend_today":
        return json.dumps(upi_tools.spend_today(), indent=2, default=str)

    elif name == "upi_spend_by_category":
        return json.dumps(
            upi_tools.spend_by_category(
                category=args.get("category"),
                days=args.get("days", 30),
            ),
            indent=2, default=str,
        )

    elif name == "upi_recent_payments":
        return json.dumps(
            upi_tools.recent_payments(n=args.get("n", 10)),
            indent=2, default=str,
        )

    elif name == "upi_top_recipients":
        return json.dumps(
            upi_tools.top_recipients(
                days=args.get("days", 30),
                limit=args.get("limit", 10),
            ),
            indent=2, default=str,
        )

    elif name == "upi_goals_status":
        return json.dumps(upi_tools.goals_status(), indent=2, default=str)

    else:
        return f"Unknown tool: {name}"


# ── Parallel read-tool execution ─────────────────────────────────────────────

def _exec_reads_parallel(calls, calendar_name: str, reminder_list: str) -> list[dict]:
    """Execute read tool calls in parallel (ThreadPoolExecutor, order-preserving).
    Returns a list of OpenAI tool-result message dicts."""
    def run(tc):
        try:
            args = json.loads(tc.function.arguments)
            return execute_tool(tc.function.name, args, calendar_name, reminder_list)
        except Exception as e:
            return f"Error: {e}"

    with ThreadPoolExecutor(max_workers=max(1, len(calls))) as pool:
        results = list(pool.map(run, calls))

    return [
        {"role": "tool", "tool_call_id": tc.id, "content": result}
        for tc, result in zip(calls, results)
    ]


# ── Agent loop ───────────────────────────────────────────────────────────────

def run_agent_loop(
    oai_messages: list[dict],
    calendar_name: str,
    reminder_list: str,
    max_iterations: int = 8,
) -> dict:
    """
    Run the agentic loop: call LLM, execute read tools automatically,
    pause on write tools for user confirmation.

    Returns:
        {
            "reply": str | None,         # Final text response (None if paused for confirmation)
            "pending_actions": list,      # Write tool calls awaiting confirmation [{name, args, call_id}]
            "assistant_msg": dict | None, # The assistant message with tool_calls (needed to resume)
        }
    """
    messages = list(oai_messages)  # don't mutate the caller's list

    for _ in range(max_iterations):
        response = _client.chat.completions.create(
            model=_model,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )
        choice = response.choices[0]

        # Model produced a final text response — done
        if choice.finish_reason == "stop":
            return {
                "reply": choice.message.content or "",
                "pending_actions": [],
                "assistant_msg": None,
            }

        # Model wants to call tools
        if choice.message.tool_calls:
            tool_calls = choice.message.tool_calls
            # Append the assistant message (with tool_calls) to history
            assistant_msg = {
                "role": "assistant",
                "content": choice.message.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Separate read vs write tool calls
            read_calls = []
            write_calls = []
            for tc in tool_calls:
                if tc.function.name in _READ_TOOLS:
                    read_calls.append(tc)
                elif tc.function.name in _WRITE_TOOLS:
                    write_calls.append(tc)

            # If there are any write tools, pause for confirmation
            # Execute read tools first, then return pending writes
            if write_calls:
                # Execute any read tools that came with the writes (in parallel)
                if read_calls:
                    messages.extend(_exec_reads_parallel(read_calls, calendar_name, reminder_list))

                # Collect write actions for confirmation
                pending = []
                for tc in write_calls:
                    args = json.loads(tc.function.arguments)
                    pending.append({
                        "name": tc.function.name,
                        "args": args,
                        "call_id": tc.id,
                    })

                # Extract reply text (model may have said something alongside the tool calls)
                reply_text = choice.message.content or ""
                if not reply_text:
                    # Generate a brief summary of what we're proposing
                    summaries = []
                    for p in pending:
                        if p["name"] == "create_event":
                            time_str = f" at {p['args']['time']}" if p['args'].get('time') else " (all day)"
                            summaries.append(f"Create event: **{p['args']['title']}** on {p['args']['date']}{time_str}")
                        elif p["name"] == "create_reminder":
                            time_str = f" at {p['args']['time']}" if p['args'].get('time') else ""
                            summaries.append(f"Create reminder: **{p['args']['title']}** due {p['args']['date']}{time_str}")
                        elif p["name"] == "move_event":
                            summaries.append(f"Move **{p['args']['original_title']}** → {p['args']['new_date']} {p['args']['new_start']}")
                        elif p["name"] == "update_reminder_date":
                            time_str = f" at {p['args']['new_time']}" if p['args'].get('new_time') else ""
                            summaries.append(f"Reschedule **{p['args']['title']}** → {p['args']['new_date']}{time_str}")
                        elif p["name"] == "delete_event":
                            summaries.append(f"Delete event: **{p['args']['title']}** on {p['args']['date']}")
                    reply_text = "Here's what I'd like to do:\n" + "\n".join(f"- {s}" for s in summaries)

                return {
                    "reply": reply_text,
                    "pending_actions": pending,
                    "assistant_msg": assistant_msg,
                }

            # Only read tools — execute in parallel and continue the loop
            messages.extend(_exec_reads_parallel(read_calls, calendar_name, reminder_list))
            continue

    # Max iterations reached — force a text response without tools.
    # Explicitly tell the model not to narrate phantom actions.
    messages.append({
        "role": "system",
        "content": (
            "You have exhausted the maximum number of reasoning steps. "
            "Summarize ONLY what was confirmed by tool results you actually received this turn. "
            "Do NOT describe actions as if they were taken if you have no tool result confirming them. "
            "State clearly what still needs to be done."
        ),
    })
    response = _client.chat.completions.create(
        model=_model,
        messages=messages,
    )
    return {
        "reply": response.choices[0].message.content or "",
        "pending_actions": [],
        "assistant_msg": None,
    }


# ── Helper: build system messages ────────────────────────────────────────────

def build_system_messages(today: str, memory_context: str, calendar_context: str = "") -> list[dict]:
    """Build the system message list for the agent loop."""
    cal_block = ""
    if calendar_context:
        cal_block = f"Your user's calendar for today:\n{calendar_context}"

    system = _SYSTEM.format(today=today, calendar_context=cal_block)
    msgs = [{"role": "system", "content": system}]

    if memory_context and memory_context.strip():
        mem_block = _MEMORY_BLOCK.format(memory_context=memory_context)
        msgs.append({"role": "system", "content": mem_block})

    return msgs


# ── Kept from old planner: edit_plan and walkthrough ─────────────────────────

_PLANNING_EDIT_SYSTEM = """You are updating a structured work plan based on the user's edit request.
Today is {today}. User is in IST (UTC+5:30).

Current plan:
{plan_json}

Apply the requested change. Return ONLY the updated plan JSON with the same structure.
Preserve task IDs where unchanged. Assign new IDs (t1, t2, ...) for new tasks."""


def edit_plan(current_plan: dict, edit_request: str, today: str) -> dict:
    """Apply a chat-based edit to a pending plan. Returns updated plan dict."""
    system = _PLANNING_EDIT_SYSTEM.format(
        today=today,
        plan_json=json.dumps(current_plan, indent=2),
    )
    response = _client.chat.completions.create(
        model=_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": edit_request},
        ],
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    try:
        updated = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse updated plan: {e}")
    return updated


def walkthrough(plan: dict) -> str:
    """Narrate the plan step-by-step with reasoning for each task."""
    response = _client.chat.completions.create(
        model=_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a planning assistant. Narrate the given plan conversationally. "
                    "For each task explain what you understood, what you assumed, and why you "
                    "chose that date and time. Be clear and specific."
                ),
            },
            {
                "role": "user",
                "content": f"Walk me through this plan:\n{json.dumps(plan, indent=2)}",
            },
        ],
    )
    return response.choices[0].message.content