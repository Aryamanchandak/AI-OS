# planner.py — Technical Documentation

**Last updated:** 2026-04-24
**Lines of code:** 486
**Language:** Python

---

## What This File Does (Plain English)

This module is the LLM brain and tool-execution layer of the application. It contains the system prompt, all seven tool schemas for OpenAI function calling, the tool dispatcher (`execute_tool`), the parallel read-tool executor, the agentic loop (`run_agent_loop`) that iterates LLM calls until a text response or write-tool confirmation is produced, and a system message builder used by both `app.py` and `scan.py`. It also retains two legacy functions (`edit_plan`, `walkthrough`) from the previous tag-parsing architecture, which are callable but not wired into the main chat flow.

---

## How It Actually Works

### Entry Points

All public functions are called from `app.py` or `scan.py`. There is no main block and no standalone execution path.

- `app.py` imports: `run_agent_loop`, `execute_tool`, `build_system_messages`
- `scan.py` imports: `run_agent_loop`, `build_system_messages`

### Data Flow

**Normal chat turn (via `app.py → run_agent_loop`):**
1. `app.py` calls `_build_oai_messages()` to assemble the full OpenAI message list (system prompt + memory block + conversation history).
2. `run_agent_loop(oai_messages, calendar_name, reminder_list)` is called in a thread.
3. Loop calls `_client.chat.completions.create(model, messages, tools=TOOL_SCHEMAS)`.
4. If `finish_reason == "stop"`: model produced text — return `{reply, pending_actions:[], assistant_msg:None}`.
5. If `finish_reason == "tool_calls"`: split tool calls into read tools (`check_calendar`, `check_reminders`) and write tools (the other five).
6. **Read tools** — execute immediately in parallel via `_exec_reads_parallel()`, append results to `messages`, continue the loop.
7. **Write tools** — if any write tools are present, pause immediately. Any read tools that arrived in the same batch are executed first, then write tools are collected as `pending_actions` and returned to the caller for user confirmation.
8. If the model produced no text alongside the write tool calls, `run_agent_loop` synthesises a human-readable summary of the proposed actions as `reply`.
9. Loop runs up to `max_iterations` (default 8). If exhausted, makes one final LLM call without the `tools` parameter to force a plain text response.

**Confirming write actions (via `app.py → execute_tool`):**
1. `app.py`'s `confirm_action` iterates `pending_actions` and calls `execute_tool(name, args, calendar_name, reminder_list)` for each.
2. `execute_tool` dispatches by tool name to the appropriate `apple_calendar` or `apple_reminders` function.
3. Returns a human-readable result string (e.g. `"Created event: Meeting on 2026-04-28"`).

**Read tools (via `_exec_reads_parallel`):**
1. Takes a list of tool call objects from the OpenAI response.
2. Uses `ThreadPoolExecutor` to call `execute_tool` for each in parallel.
3. Returns a list of OpenAI `tool` role message dicts with results, preserving order.
4. Errors inside individual tool calls are caught per-call and returned as `"Error: <message>"` strings — they do not abort the batch.

### State Management

Module-level constants only. No mutable state:
- `_client` — OpenAI client, initialized once at import.
- `_model = "gpt-4o"` — valid model name used for all agent loop calls, `edit_plan`, and `walkthrough`.
- `TOOL_SCHEMAS` — the seven tool definitions passed to the OpenAI API on every agent loop call.
- `_READ_TOOLS = {"check_calendar", "check_reminders"}` — auto-executed set.
- `_WRITE_TOOLS = {"create_event", "create_reminder", "move_event", "update_reminder_date", "delete_event"}` — pause-for-confirmation set.
- `_SYSTEM` — main system prompt template with `{today}` and `{calendar_context}` placeholders.
- `_MEMORY_BLOCK` — secondary system message template with `{memory_context}` placeholder.
- `_PLANNING_EDIT_SYSTEM` — legacy system prompt for `edit_plan`.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `execute_tool(name, args, calendar_name, reminder_list)` | Dispatches a named tool call to the appropriate `apple_calendar` or `apple_reminders` function. Returns a result string. Raises `RuntimeError` on AppleScript failure. Returns `"Unknown tool: <name>"` for unknown tools (not an exception). |
| `_exec_reads_parallel(calls, calendar_name, reminder_list)` | Executes a list of read tool calls concurrently using `ThreadPoolExecutor`. Returns a list of OpenAI `{"role": "tool", ...}` dicts. Per-call errors become error strings, not exceptions. |
| `run_agent_loop(oai_messages, calendar_name, reminder_list, max_iterations)` | The core agentic loop. Iterates LLM calls, auto-executes reads in parallel, pauses on writes. Returns `{reply, pending_actions, assistant_msg}`. |
| `build_system_messages(today, memory_context, calendar_context)` | Builds a list of system message dicts: one with the main prompt (today + calendar context), optionally a second with the memory block. Used by both `app.py` and `scan.py`. |
| `edit_plan(current_plan, edit_request, today)` | Legacy: sends a plan dict + edit instruction to the LLM with `response_format=json_object`. Returns updated plan dict. Raises `ValueError` on parse failure. Not called from the active chat flow. |
| `walkthrough(plan)` | Legacy: asks the LLM to narrate a plan dict conversationally. Returns raw string. Not called from the active chat flow. |

### Tool Schemas (TOOL_SCHEMAS)

Seven tools are defined:

| Tool name | Type | Required params | Optional params |
|---|---|---|---|
| `check_calendar` | Read | — | `days_ahead` (int, default 7) |
| `check_reminders` | Read | — | `list_name` (str) |
| `create_event` | Write | `title`, `date` | `time`, `duration_minutes`, `description` |
| `create_reminder` | Write | `title`, `date`, `time` | `description` |
| `move_event` | Write | `original_title`, `original_date`, `original_start`, `new_date`, `new_start` | `duration_minutes` |
| `update_reminder_date` | Write | `title`, `list_name`, `new_date` | `new_time` |
| `delete_event` | Write | `title`, `date` | — |

### execute_tool Dispatch Logic

| Tool name | What it calls |
|---|---|
| `check_calendar` | `get_today_events` if `days_ahead <= 1`, else `get_week_events` |
| `check_reminders` | `list_open_reminders(list_name)` if `list_name` provided, else `list_all_open_reminders()` |
| `create_event` | `create_timed_event` if `time` arg present, else `create_allday_event` |
| `create_reminder` | `ensure_list(reminder_list)` then `create_reminder(...)` — always writes to the env-configured list, ignoring any list the user may have intended |
| `move_event` | `apple_calendar.move_event(...)` |
| `update_reminder_date` | `apple_reminders.update_reminder_date(...)` |
| `delete_event` | `apple_calendar.delete_event(...)` |

### External Dependencies

- **OpenAI API** — `chat.completions.create` with `tools=TOOL_SCHEMAS`. All calls synchronous. No streaming.
- **`_model = "gpt-4o"`** — valid model.
- **`apple_calendar`** — `get_today_events`, `get_week_events`, `create_timed_event`, `create_allday_event`, `move_event`, `delete_event`.
- **`apple_reminders`** — `list_open_reminders`, `list_all_open_reminders`, `ensure_list`, `create_reminder`, `update_reminder_date`.
- **`json`**, **`os`**, **`datetime`**, **`concurrent.futures.ThreadPoolExecutor`** from standard library.
- **`python-dotenv`**.

### Error Handling

| Failure | Handling |
|---|---|
| `execute_tool` — AppleScript fails | `RuntimeError` propagates to caller (either `_exec_reads_parallel` which catches it, or `app.py` which handles it) |
| `_exec_reads_parallel` — per-call exception | Caught per call, result becomes `"Error: <msg>"` string — loop continues |
| `run_agent_loop` — OpenAI API error | Not caught — propagates to `app.py`'s `asyncio.to_thread` caller |
| `run_agent_loop` — unknown tool in response | Returns `"Unknown tool: <name>"` string as tool result, loop continues |
| `run_agent_loop` — max iterations hit | Makes one final LLM call without tools to force a text response |
| `edit_plan` — JSON parse fails | Raises `ValueError` |
| `walkthrough` — API error | Not caught — propagates to `app.py` |

---

## Non-Technical Decisions Embedded in the Code

- **Read tools auto-execute, write tools pause** — this is the core architectural choice. `_READ_TOOLS` and `_WRITE_TOOLS` are the sets that drive this split. Any tool added to the schemas must also be added to one of these sets or it will be silently ignored in the loop (falls through to neither branch, no result appended to messages, loop stalls).
- **Read tools run in parallel via `ThreadPoolExecutor`** — this is thread-based parallelism on top of blocking `NSTask` AppleScript calls. Threading + NSTask is explicitly safe on macOS (no fork). This is the correct design choice given the CLAUDE.md fork() warning.
- **Write tools in the same batch as reads** — if the model requests `check_calendar` and `create_event` in the same tool_calls batch, the reads execute first (in parallel), and then the write tools are surfaced as pending. The reads' results are appended to `messages` but the assistant message with the tool_calls is also preserved — this is the `pending_assistant_msg` that `app.py` stores and uses to resume the loop after confirmation.
- **Fallback reply synthesis** — if the model emits write tool calls with no text content, `run_agent_loop` generates a formatted summary (e.g. "Create event: **Meeting** on 2026-04-28 at 10:00") from the pending actions. This ensures the user always sees something descriptive in the confirmation card even if the model was terse.
- **`create_reminder` always uses `reminder_list` from env** — the tool schema exposes no `list_name` parameter. Every reminder created through the agent always goes to the single configured list. Users cannot direct reminders to different lists via chat.
- **IST (UTC+5:30) is hardcoded in the system prompt** — not read from the system timezone. If the user is not in IST, date reasoning will be wrong for timezone-edge queries (e.g. "tomorrow at midnight").
- **`_model = "gpt-4o"` for all agent loop calls** — the full `gpt-4o` model is used (not mini) because the agent loop involves function calling and multi-step reasoning that benefits from the larger model's capability.
- **Legacy `edit_plan` and `walkthrough` are retained** — these remain callable but are not wired into any active endpoint in `app.py`. They use `response_format={"type": "json_object"}` and a separate system prompt. Their presence means `planner.py` imports survive without changes if these were re-enabled.

---

## Honest Gaps and Risks

- **No retry on OpenAI API failures** — if the API returns a rate limit or transient 5xx error, the exception propagates immediately. `app.py` does not catch it in the `/chat` handler, so the user sees a 500 error.
- **`session["messages"]` grows unbounded** — `run_agent_loop` receives the full history on every call. Very long sessions will hit the `gpt-4o` context window limit (128k tokens). This will produce an OpenAI API error that propagates uncaught.
- **`max_iterations=8` is generous but finite** — if the model loops through 8 read-only tool calls without returning text, the final bare LLM call produces a response without tool awareness. In practice this shouldn't happen with the current tools, but it is a silent floor.
- **Unknown tool name in model response returns a non-error string** — `"Unknown tool: <name>"` is appended to messages as a tool result and the loop continues. The model may hallucinate a tool name and receive a confusing result, potentially causing odd behavior in subsequent turns.
- **Read tools that fail inside `_exec_reads_parallel` return error strings** — the loop continues but the model receives `"Error: <msg>"` as the tool result. It may then attempt a write action based on the assumption that the read succeeded. This could cause incorrect write proposals.
- **`edit_plan` is not connected to the active flow** — if re-enabled, note that it does not use `TOOL_SCHEMAS` or the agent loop; it expects a plain plan dict and returns an updated one. It is disconnected from the tool-calling architecture.
- **The system prompt is injected fresh on every call** via `build_system_messages` — today's date and calendar context are always current. But the full conversation history is rebuilt from `session["messages"]` in `app.py`, not managed within `run_agent_loop`. This means the agent loop has no way to trim or summarize old history.
- **`_exec_reads_parallel` with one tool call uses one thread** — `max_workers=max(1, len(calls))`. With a single read tool, there is no parallelism benefit, just the overhead of thread creation.

---

## Developer Notes

- When adding a new tool, you must: (1) add its schema to `TOOL_SCHEMAS`, (2) add its name to either `_READ_TOOLS` or `_WRITE_TOOLS`, (3) add its dispatch case to `execute_tool`. If you miss step 2, the tool will be silently skipped in the loop.
- When editing the system prompt `_SYSTEM`, note it uses `.format(today=today, calendar_context=cal_block)` in `build_system_messages`. Any literal `{` or `}` in the template string must be doubled to `{{` and `}}` to avoid `KeyError`.
- `build_system_messages` is shared between `app.py` (chat flow) and `scan.py` (daily scan). Changes to the system prompt affect both paths.
- The `assistant_msg` returned in `pending_actions` scenarios is a manually-assembled dict (not the raw OpenAI response object). It must preserve the `tool_calls` field in the exact format OpenAI expects for the resume-after-confirm path in `app.py`. Do not simplify or reformat it.
- `execute_tool` does not call `ensure_list` for `update_reminder_date` — the assumption is the list already exists. If a user somehow triggers `update_reminder_date` for a list that was deleted since the reminder was created, the AppleScript will error.
