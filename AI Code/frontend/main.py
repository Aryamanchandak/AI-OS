import os
import json
import asyncio
import datetime
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import sys
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Fix imports: app_1.py was moved to top-level but modules live one level down
_PLANNER_DIR = Path(__file__).parent / "Planner and Reminders" / "Calendar and Reminders"
sys.path.insert(0, str(_PLANNER_DIR))

from planner import run_agent_loop, execute_tool, build_system_messages
from apple_calendar import get_today_events, get_week_events, delete_event, move_event as move_event_fn
from apple_calendar import create_timed_event, create_allday_event
from apple_reminders import ensure_list, delete_reminder, list_all_open_reminders
from apple_reminders import update_reminder_date as update_reminder_date_fn
from scan import run_daily_scan
from memory import load_memory_context, save_session

# UPI brain layer — optional. Imported lazily so a missing/broken brain
# install doesn't take down the main planning assistant.
try:
    from brain.dashboard import app as upi_app  # FastAPI sub-app
    _UPI_DASHBOARD_OK = True
except Exception as _e:  # noqa: BLE001
    upi_app = None
    _UPI_DASHBOARD_OK = False
    logging.getLogger(__name__).warning(
        "UPI dashboard not available (will skip /upi mount): %s", _e
    )

try:
    from brain import agent as upi_agent  # for /daily ingestion
    _UPI_AGENT_OK = True
except Exception as _e:  # noqa: BLE001
    upi_agent = None
    _UPI_AGENT_OK = False
    logging.getLogger(__name__).warning(
        "UPI agent not available (will skip ingestion in /daily): %s", _e
    )

load_dotenv()

# Anthropic client for optimizer
try:
    import anthropic as _anthropic_lib
    _anthropic = _anthropic_lib.Anthropic()
    _ANTHROPIC_OK = True
except Exception as _ae:
    _anthropic = None
    _ANTHROPIC_OK = False
    logging.getLogger(__name__).warning("Anthropic SDK not available (optimizer disabled): %s", _ae)


CALENDAR_NAME = os.getenv("APPLE_CALENDAR_NAME", "Calendar")
REMINDER_LIST = os.getenv("APPLE_REMINDER_LIST", "Work Tracker")

BASE_DIR = Path(__file__).parent
PENDING_STATE_FILE = BASE_DIR / "pending_state.json"
SYNC_STATE_FILE = BASE_DIR / "sync_state.json"

# ── Session state ────────────────────────────────────────────────────────────

session: dict = {
    "messages": [{"role": "ai", "content": "Hi! What's on your mind?"}],
    "oai_messages": [],            # OpenAI-format history (built fresh each call from messages)
    "pending_actions": [],         # write tool calls awaiting confirmation
    "pending_assistant_msg": None, # assistant message with tool_calls (for resuming after confirm)
    "session_start_time": datetime.datetime.now(),
    "memory_context": "",
}


# ── Pending-state persistence ────────────────────────────────────────────────

def _save_pending_state() -> None:
    try:
        with open(PENDING_STATE_FILE, "w") as f:
            json.dump({
                "pending_actions": session["pending_actions"],
                "pending_assistant_msg": session["pending_assistant_msg"],
                "messages": session["messages"],
            }, f)
    except Exception as e:
        logging.getLogger(__name__).warning("Could not save pending state: %s", e)


def _clear_pending_state() -> None:
    try:
        PENDING_STATE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _load_pending_state() -> None:
    try:
        if PENDING_STATE_FILE.exists():
            with open(PENDING_STATE_FILE) as f:
                data = json.load(f)
            session["pending_actions"] = data.get("pending_actions", [])
            session["pending_assistant_msg"] = data.get("pending_assistant_msg")
            loaded_msgs = data.get("messages", [])
            if loaded_msgs:
                session["messages"] = loaded_msgs
    except Exception:
        pass


# ── Sync-state helpers (Calendar ↔ Reminder linking) ────────────────────────

def _load_sync_state() -> dict:
    try:
        if SYNC_STATE_FILE.exists():
            with open(SYNC_STATE_FILE) as f:
                return json.load(f)
    except Exception as e:
        logging.getLogger(__name__).warning("Could not load sync state: %s", e)
    return {"links": []}


def _save_sync_state(state: dict) -> None:
    try:
        with open(SYNC_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logging.getLogger(__name__).warning("Could not save sync state: %s", e)


def _find_linked_reminders(event_title: str, event_date: str, state: dict) -> list:
    """Return reminder dicts linked to the given event title+date."""
    for link in state.get("links", []):
        if link.get("event_title") == event_title and link.get("event_date") == event_date:
            return link.get("reminders", [])
    return []


def _update_sync_link_date(event_title: str, old_date: str, new_date: str, state: dict) -> dict:
    """Update the event_date of a sync link after a move_event is confirmed."""
    for link in state.get("links", []):
        if link.get("event_title") == event_title and link.get("event_date") == old_date:
            link["event_date"] = new_date
            for r in link.get("reminders", []):
                r["due_date"] = new_date
            break
    return state


def _remove_sync_link(event_title: str, event_date: str, state: dict) -> dict:
    """Remove a sync link after a delete_event is confirmed."""
    state["links"] = [
        lnk for lnk in state.get("links", [])
        if not (lnk.get("event_title") == event_title and lnk.get("event_date") == event_date)
    ]
    return state


def _add_sync_link(event_title: str, event_date: str, reminders: list, state: dict) -> dict:
    """Add or merge a sync link entry."""
    for link in state.get("links", []):
        if link.get("event_title") == event_title and link.get("event_date") == event_date:
            existing_titles = {r["title"] for r in link.get("reminders", [])}
            for r in reminders:
                if r["title"] not in existing_titles:
                    link.setdefault("reminders", []).append(r)
            return state
    state.setdefault("links", []).append({
        "event_title": event_title,
        "event_date": event_date,
        "reminders": list(reminders),
    })
    return state


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_today_calendar_context() -> str:
    """Fetch today's events for ambient calendar awareness. Returns '' on failure."""
    try:
        events = get_today_events(CALENDAR_NAME)
        if not events:
            return "No events scheduled for today."
        lines = []
        for e in events:
            if e.get("allday"):
                lines.append(f"- {e['title']} (all day)")
            else:
                lines.append(f"- {e['title']} ({e['start']}–{e['end']})")
        return "\n".join(lines)
    except Exception:
        return ""


def _build_oai_messages() -> list[dict]:
    """Convert session messages to OpenAI format with system prompt."""
    today = datetime.date.today().isoformat()
    calendar_context = _get_today_calendar_context()
    system_msgs = build_system_messages(today, session["memory_context"], calendar_context)

    oai = list(system_msgs)
    for m in session["messages"]:
        role = "user" if m["role"] == "user" else "assistant"
        oai.append({"role": role, "content": m["content"]})
    return oai


def _actions_to_frontend(actions: list) -> list[dict]:
    """Convert pending_actions to a frontend-friendly format."""
    result = []
    for a in actions:
        item = {"tool": a["name"], **a["args"]}
        result.append(item)
    return result


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    session["memory_context"] = load_memory_context()
    _load_pending_state()
    yield
    if len(session["messages"]) > 1:
        try:
            save_session(
                messages=session["messages"],
                modes_visited=["chat"],  # simplified — no mode tracking
                current_plan=None,
                session_start_time=session["session_start_time"],
            )
        except Exception:
            pass


_STATIC_DIR = BASE_DIR / "static"
_STATIC_DIR.mkdir(exist_ok=True)

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Mount the UPI ledger dashboard under /upi if the brain layer is available.
if _UPI_DASHBOARD_OK and upi_app is not None:
    app.mount("/upi", upi_app, name="upi")


@app.get("/")
async def root():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


@app.get("/state")
async def get_state():
    return {
        "messages": session["messages"],
        "actions": _actions_to_frontend(session["pending_actions"]) if session["pending_actions"] else None,
        "confirm": bool(session["pending_actions"]),
    }


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
async def chat(req: ChatRequest):
    msg = req.message
    session["messages"].append({"role": "user", "content": msg})

    # Build OpenAI messages from full conversation
    oai_messages = _build_oai_messages()

    # Run the agent loop (blocking — runs in thread for async compat)
    try:
        result = await asyncio.to_thread(
            run_agent_loop, oai_messages, CALENDAR_NAME, REMINDER_LIST,
        )
    except Exception as e:
        logging.getLogger(__name__).error("Agent loop failed: %s", e)
        session["messages"].pop()  # remove the appended user message so history stays clean
        return {"reply": "Something went wrong — please try again.", "actions": None, "confirm": False}

    reply = result["reply"] or ""
    pending = result["pending_actions"]

    if pending:
        session["pending_actions"] = pending
        session["pending_assistant_msg"] = result["assistant_msg"]
        _save_pending_state()

    session["messages"].append({"role": "ai", "content": reply})

    return {
        "reply": reply,
        "actions": _actions_to_frontend(pending) if pending else None,
        "confirm": bool(pending),
    }


# ── Confirm / Cancel actions ────────────────────────────────────────────────

@app.post("/confirm_action")
async def confirm_action():
    actions = session.get("pending_actions", [])
    if not actions:
        return {"reply": "No pending actions to confirm.", "actions": None, "confirm": False}

    ensure_list(REMINDER_LIST)
    rollback_stack = []
    tool_results = []  # list of (call_id, result_str)
    error_reply = None

    for action in actions:
        name = action["name"]
        args = action["args"]
        call_id = action.get("call_id", "")

        # Pre-read snapshot for destructive operations (enables rollback)
        pre_snapshot = None
        if name == "delete_event":
            try:
                pre_events = get_week_events(CALENDAR_NAME)
                matching = [
                    e for e in pre_events
                    if e.get("title") == args["title"] and e.get("date") == args["date"]
                ]
                if matching:
                    pre_snapshot = matching[0]
            except Exception:
                pass
        elif name == "update_reminder_date":
            try:
                all_reminders = list_all_open_reminders()
                matching = [
                    r for r in all_reminders
                    if r.get("title") == args["title"] and r.get("list") == args.get("list_name")
                ]
                if matching:
                    pre_snapshot = matching[0]
            except Exception:
                pass

        try:
            result_str = execute_tool(name, args, CALENDAR_NAME, REMINDER_LIST)
            tool_results.append((call_id, result_str))

            if name == "create_event":
                rollback_stack.append(("delete_event", args["title"], args["date"]))
            elif name == "create_reminder":
                rollback_stack.append(("delete_reminder", args["title"], REMINDER_LIST))
            elif name == "move_event":
                rollback_stack.append(("move_event_back", args))
            elif name == "delete_event" and pre_snapshot:
                rollback_stack.append(("recreate_event", pre_snapshot))
            elif name == "update_reminder_date" and pre_snapshot:
                rollback_stack.append((
                    "revert_reminder_date",
                    args["title"],
                    args.get("list_name", REMINDER_LIST),
                    pre_snapshot.get("due") or "",
                ))
            else:
                rollback_stack.append(None)

        except Exception as e:
            rollback_errors = []
            for undo in reversed(rollback_stack):
                if undo is None:
                    continue
                try:
                    if undo[0] == "delete_event":
                        delete_event(undo[1], undo[2], CALENDAR_NAME)
                    elif undo[0] == "delete_reminder":
                        delete_reminder(undo[1], undo[2])
                    elif undo[0] == "move_event_back":
                        a = undo[1]
                        move_event_fn(
                            a["original_title"], a["new_date"], a["new_start"],
                            a["original_date"], a["original_start"],
                            a.get("duration_minutes", 60), CALENDAR_NAME,
                        )
                    elif undo[0] == "recreate_event":
                        evt = undo[1]
                        if evt.get("allday"):
                            create_allday_event(evt["title"], evt["date"], "", CALENDAR_NAME)
                        else:
                            # Calculate duration from start/end strings (HH:MM)
                            try:
                                sh, sm = map(int, evt["start"].split(":"))
                                eh, em = map(int, evt["end"].split(":"))
                                duration = max(30, (eh * 60 + em) - (sh * 60 + sm))
                            except Exception:
                                duration = 60
                            create_timed_event(
                                evt["title"], evt["date"], evt["start"], duration, "", CALENDAR_NAME
                            )
                    elif undo[0] == "revert_reminder_date":
                        _, r_title, r_list, old_due = undo
                        if old_due:
                            update_reminder_date_fn(r_title, r_list, old_due, "")
                except Exception as ue:
                    rollback_errors.append(str(ue))

            cleanup_note = ""
            if rollback_errors:
                cleanup_note = f" Cleanup partial — {len(rollback_errors)} undo(s) also failed."
            elif rollback_stack:
                cleanup_note = " Previously created items have been cleaned up."

            error_reply = f"Failed on \"{args.get('title', '?')}\": {e}{cleanup_note}"
            break

    # ── Update sync state after successful batch ─────────────────────────────
    if not error_reply:
        sync_state = _load_sync_state()

        # Find any create_event in this batch
        created_events = [
            a for a in actions if a["name"] == "create_event"
        ]
        created_reminders = [
            a for a in actions if a["name"] == "create_reminder"
        ]

        # Link reminders to events when confirmed together in same batch
        for evt_action in created_events:
            evt_title = evt_action["args"]["title"]
            evt_date = evt_action["args"]["date"]
            linked_reminders = []
            for rem_action in created_reminders:
                rem_title = rem_action["args"]["title"]
                # Link if titles share a substring or they're in the same batch
                linked_reminders.append({
                    "title": rem_title,
                    "list": REMINDER_LIST,
                    "due_date": rem_action["args"].get("date", evt_date),
                    "due_time": rem_action["args"].get("time", ""),
                })
            if linked_reminders:
                sync_state = _add_sync_link(evt_title, evt_date, linked_reminders, sync_state)

        # Handle move_event: update sync link date and queue reminder updates
        move_actions = [a for a in actions if a["name"] == "move_event"]
        sync_reminder_updates = []
        for mv_action in move_actions:
            orig_title = mv_action["args"]["original_title"]
            orig_date = mv_action["args"]["original_date"]
            new_date = mv_action["args"]["new_date"]
            linked = _find_linked_reminders(orig_title, orig_date, sync_state)
            if linked:
                sync_state = _update_sync_link_date(orig_title, orig_date, new_date, sync_state)
                for r in linked:
                    sync_reminder_updates.append({
                        "name": "update_reminder_date",
                        "args": {
                            "title": r["title"],
                            "list_name": r.get("list", REMINDER_LIST),
                            "new_date": new_date,
                            "new_time": r.get("due_time", ""),
                        },
                        "call_id": f"sync_{r['title'][:20]}",
                    })

        # Handle delete_event: queue reminder deletions
        delete_actions = [a for a in actions if a["name"] == "delete_event"]
        for del_action in delete_actions:
            del_title = del_action["args"]["title"]
            del_date = del_action["args"]["date"]
            linked = _find_linked_reminders(del_title, del_date, sync_state)
            if linked:
                sync_state = _remove_sync_link(del_title, del_date, sync_state)
                for r in linked:
                    sync_reminder_updates.append({
                        "name": "delete_reminder",
                        "args": {
                            "title": r["title"],
                            "list_name": r.get("list", REMINDER_LIST),
                        },
                        "call_id": f"sync_del_{r['title'][:20]}",
                    })

        _save_sync_state(sync_state)
    else:
        sync_reminder_updates = []

    # Grab and clear pending state before re-entering the loop
    pending_assistant_msg = session["pending_assistant_msg"]
    session["pending_actions"] = []
    session["pending_assistant_msg"] = None
    _clear_pending_state()

    if error_reply:
        session["messages"].append({"role": "ai", "content": error_reply})
        return {"reply": error_reply, "actions": None, "confirm": False}

    # Re-enter agent loop so the model sees write results and can chain further.
    new_pending = []
    if pending_assistant_msg is not None:
        base_msgs = _build_oai_messages()
        if base_msgs and base_msgs[-1].get("role") == "assistant":
            base_msgs = base_msgs[:-1]
        resume_msgs = (
            base_msgs
            + [pending_assistant_msg]
            + [{"role": "tool", "tool_call_id": cid, "content": res} for cid, res in tool_results]
        )
        try:
            loop_result = await asyncio.to_thread(
                run_agent_loop, resume_msgs, CALENDAR_NAME, REMINDER_LIST
            )
            reply = loop_result["reply"] or "Done!"
            new_pending = loop_result.get("pending_actions", [])
            if new_pending:
                session["pending_actions"] = new_pending
                session["pending_assistant_msg"] = loop_result["assistant_msg"]
                _save_pending_state()
        except Exception as e:
            # Writes already committed — don't let a follow-up error obscure that
            summary = "\n".join(f"- {res}" for _, res in tool_results)
            reply = f"Done! Here's what I did:\n{summary}\n\n(Follow-up failed: {e})"
    else:
        summary = "\n".join(f"- {res}" for _, res in tool_results)
        reply = f"Done! Here's what I did:\n{summary}"

    # Append sync-driven reminder updates as additional pending actions
    if sync_reminder_updates and not new_pending:
        n = len(sync_reminder_updates)
        noun = "reminder" if n == 1 else "reminders"
        reply += f"\n\nThis event had {n} linked {noun}. I've queued updates — confirm to apply them too."
        new_pending = sync_reminder_updates
        session["pending_actions"] = new_pending
        session["pending_assistant_msg"] = None
        _save_pending_state()

    session["messages"].append({"role": "ai", "content": reply})
    return {
        "reply": reply,
        "actions": _actions_to_frontend(new_pending) if new_pending else None,
        "confirm": bool(new_pending),
    }


@app.post("/cancel_action")
async def cancel_action():
    session["pending_actions"] = []
    session["pending_assistant_msg"] = None
    _clear_pending_state()
    reply = "Cancelled — no changes made."
    session["messages"].append({"role": "ai", "content": reply})
    return {"reply": reply, "actions": None, "confirm": False}


# ── Daily scan ───────────────────────────────────────────────────────────────

@app.post("/daily")
async def daily():
    # Run UPI ingestion first (best-effort). A missing chat.db, denied Full
    # Disk Access, or any other failure must NOT break the calendar/reminder
    # daily scan that follows.
    upi_note = ""
    if _UPI_AGENT_OK and upi_agent is not None:
        try:
            await asyncio.to_thread(upi_agent.run)
        except Exception as e:  # noqa: BLE001
            logging.getLogger(__name__).warning("UPI ingestion failed: %s", e)
            upi_note = f"\n\n_(UPI ingestion skipped: {e})_"

    try:
        result = await asyncio.to_thread(
            run_daily_scan, CALENDAR_NAME, REMINDER_LIST, session["memory_context"],
        )
    except Exception as e:
        result = {"reply": f"Daily scan failed: {str(e)}", "pending_actions": [], "assistant_msg": None}

    if upi_note and result.get("reply") is not None:
        result["reply"] = (result["reply"] or "") + upi_note

    reply = result["reply"] or "Nothing to report."
    pending = result.get("pending_actions", [])

    if pending:
        session["pending_actions"] = pending
        session["pending_assistant_msg"] = result.get("assistant_msg")
        _save_pending_state()

    session["messages"].append({"role": "ai", "content": reply})
    return {
        "reply": reply,
        "actions": _actions_to_frontend(pending) if pending else None,
        "confirm": bool(pending),
    }


# ── New session ──────────────────────────────────────────────────────────────

@app.post("/new_session")
async def new_session():
    if len(session["messages"]) > 1:
        try:
            save_session(
                messages=session["messages"],
                modes_visited=["chat"],
                current_plan=None,
                session_start_time=session["session_start_time"],
            )
        except Exception:
            pass
    _clear_pending_state()
    session.update({
        "messages": [{"role": "ai", "content": "Hi! What's on your mind?"}],
        "oai_messages": [],
        "pending_actions": [],
        "pending_assistant_msg": None,
        "session_start_time": datetime.datetime.now(),
        "memory_context": load_memory_context(),
    })
    return {"reply": "Session saved. Starting fresh!", "actions": None, "confirm": False}


# ══════════════════════════════════════════════════════════════════════════════
# ── Optimizer (Phase B) ───────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

# ── Prompt constants (ported verbatim from prompt-plan-optimizer/lib/prompts.ts) ──

def _PROMPT_SECTION_DETECTOR(mode: str) -> str:
    kind_list = (
        "one of: system | role | context | examples | output_format | constraints | other"
        if mode == "prompt"
        else "one of: phase | module | criteria | rationale | overview | other"
    )
    doc_type = "prompt" if mode == "prompt" else "technical plan written in markdown"
    return f"""You are splitting a {doc_type} into its constituent sections.

Return ONLY valid JSON with this exact schema:
{{
  "sections": [
    {{
      "title": "short label, 2-6 words",
      "kind": "{kind_list}",
      "content": "VERBATIM text from the input — do not paraphrase or summarize",
      "rationale": "one sentence explaining why this section exists as a distinct unit"
    }}
  ]
}}

Splitting rules:
- Prefer splitting on existing markdown headers (# / ## / ###) when present.
- Otherwise split on semantic boundaries: role changes, topic shifts, phase transitions.
- Each section should be 1-3 paragraphs typically. Merge tiny fragments. Split overly long sections at natural sub-topics.
- The "content" field MUST contain the original text exactly as written. Do not edit, clean up, or rephrase.
- The "rationale" is what the user reads when they ask "why is this section here?" — make it about purpose, not just description.
- 80% of users should accept your splits without reorganizing. Aim for clarity over cleverness.

If the input has no clear structure, fall back to one section with kind="other"."""


_PROMPT_CONTEXT_EXTRACTOR = """You are extracting structured project context from a user's freeform dump.

Return ONLY valid JSON with this exact schema:
{
  "goal": "one or two sentences on what is being built and why",
  "tech_stack": ["array", "of", "technologies"],
  "constraints": ["array of constraints — deadlines, infra limits, things off-limits, team size"],
  "key_decisions": ["decisions already made that should not be re-litigated"],
  "architecture_notes": "any load-bearing architectural notes, or empty string",
  "open_questions": ["things the user explicitly hasn't decided yet"]
}

Rules:
- Use empty array or empty string for fields with no info. Do not invent.
- Be terse. This is going into a system prompt, not a report."""


def _PROMPT_ITERATION(
    mode: str,
    project_context: dict | None,
    full_document: str,
    current_section: dict,
    chat_history: list[dict],
    user_message: str,
) -> str:
    ctx_str = json.dumps(project_context, indent=2) if project_context else "(no context provided yet)"
    history_str = (
        "(this is the first message)"
        if not chat_history
        else "\n".join(f"{m['role']}: {m['text']}" for m in chat_history)
    )
    return f"""You are helping a user iterate on one section of a {('prompt' if mode == 'prompt' else 'plan')}. The user has clicked into this section and is asking you to explain it, change it, or push back on it.

PROJECT CONTEXT:
{ctx_str}

FULL DOCUMENT (for cross-section awareness):
{full_document}

CURRENT SECTION YOU'RE WORKING ON:
Title: {current_section['title']}
Kind: {current_section['kind']}
Rationale: {current_section['rationale']}
Content:
\"\"\"
{current_section['content']}
\"\"\"

CHAT HISTORY FOR THIS SECTION:
{history_str}

USER'S CURRENT MESSAGE:
{user_message}

Return ONLY valid JSON with this exact schema:
{{
  "rewritten_content": "the new content for this section — or unchanged if you're asking a question or just explaining",
  "reasoning": "your reasoning for this response in plain English",
  "clarifying_question": "a question to ask the user, OR null if you don't need to ask anything",
  "suggested_context_update": "a project-context update inferred from the chat, OR null"
}}

Behavior rules:
- If the user is asking WHY a section is the way it is, put your explanation in "reasoning" and leave "rewritten_content" unchanged.
- If the user is asking you to change the section, rewrite it in "rewritten_content" and explain the change in "reasoning".
- If the user's request is ambiguous OR you lack project context, ASK A QUESTION via "clarifying_question" and leave "rewritten_content" unchanged.
- Stay in scope. Don't rewrite other sections — only this one."""


def _PROMPT_CONFLICT_DETECTOR(sections: list[dict], edited_section_id: str, project_context: dict | None) -> str:
    ctx_str = json.dumps(project_context, indent=2) if project_context else "(none)"
    sections_str = "\n\n---\n\n".join(
        f"[{'EDITED' if s['id'] == edited_section_id else 'OK'}] §{s['id']} {s['title']}\n{s['content']}"
        for s in sections
    )
    return f"""You are checking a plan for cross-section conflicts after a recent edit. The user just edited the section marked [EDITED] below.

PROJECT CONTEXT:
{ctx_str}

SECTIONS:
{sections_str}

Return ONLY valid JSON with this exact schema:
{{
  "conflicts": [
    {{
      "section_id": "id of the section that conflicts with the edit",
      "type": "contradiction | redundancy | orphan",
      "description": "one sentence on what the conflict is"
    }}
  ]
}}

Definitions:
- contradiction: the edited section now says X, another section still says not-X.
- redundancy: the edited section now overlaps significantly with another section.
- orphan: the edited section removed or changed something another section still references.

Rules:
- Only flag REAL conflicts. Empty conflicts array if there are none. Do not invent issues."""


# ── Utility functions ─────────────────────────────────────────────────────────

def diff_lines(old: str, new: str) -> list[dict]:
    """LCS-based line diff. Returns [{type: add|remove|equal, text}]."""
    old_lines = (old or "").split("\n")
    new_lines = (new or "").split("\n")
    m, n = len(old_lines), len(new_lines)

    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if old_lines[i - 1] == new_lines[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    result: list[dict] = []
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and old_lines[i - 1] == new_lines[j - 1]:
            result.insert(0, {"type": "equal", "text": old_lines[i - 1]})
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            result.insert(0, {"type": "add", "text": new_lines[j - 1]})
            j -= 1
        else:
            result.insert(0, {"type": "remove", "text": old_lines[i - 1]})
            i -= 1
    return result


def _call_claude_json(system: str, user_msg: str, max_tokens: int = 4000) -> dict:
    if not _ANTHROPIC_OK or _anthropic is None:
        raise RuntimeError("Anthropic SDK not available")
    msg = _anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0].strip()
    return json.loads(raw)


def _opt_detect_sections(raw_input: str, mode: str) -> list[dict]:
    result = _call_claude_json(_PROMPT_SECTION_DETECTOR(mode), raw_input, max_tokens=4000)
    return [
        {
            "id": f"s{i + 1}",
            "title": s["title"],
            "kind": s["kind"],
            "content": s["content"],
            "rationale": s["rationale"],
            "history": [],
        }
        for i, s in enumerate(result["sections"])
    ]


def _opt_iterate_section(
    mode: str,
    section: dict,
    full_document: str,
    project_context: dict | None,
    chat_history: list[dict],
    user_message: str,
) -> dict:
    system = _PROMPT_ITERATION(mode, project_context, full_document, section, chat_history, user_message)
    result = _call_claude_json(system, user_message, max_tokens=3000)
    return {
        "rewrittenContent": result["rewritten_content"],
        "reasoning": result["reasoning"],
        "clarifyingQuestion": result.get("clarifying_question"),
        "suggestedContextUpdate": result.get("suggested_context_update"),
    }


def _opt_detect_conflicts(sections: list[dict], edited_section_id: str, project_context: dict | None) -> list[dict]:
    system = _PROMPT_CONFLICT_DETECTOR(sections, edited_section_id, project_context)
    result = _call_claude_json(system, "Check for conflicts now.", max_tokens=1500)
    return result.get("conflicts", [])


def _opt_full_document(sections: list[dict]) -> str:
    return "\n\n".join(f"## {s['title']}\n{s['content']}" for s in sections)


# ── Optimizer in-memory state ─────────────────────────────────────────────────

opt_state: dict = {
    "documents": {},   # doc_id -> {id, mode, raw_input, sections, context}
    "versions": {},    # doc_id -> [{timestamp, sections_snapshot, conflicts}]
    "chat": {},        # section_id -> [{role, text}]
}


# ── Pydantic models ───────────────────────────────────────────────────────────

class OptNewDocRequest(BaseModel):
    raw_input: str
    mode: str = "plan"


class OptIterateRequest(BaseModel):
    doc_id: str
    section_id: str
    message: str


class OptContextRequest(BaseModel):
    doc_id: str
    context_text: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/optimizer/new_doc")
async def opt_new_doc(req: OptNewDocRequest):
    if not _ANTHROPIC_OK:
        raise HTTPException(503, "Anthropic SDK not installed — run: pip install anthropic")
    if req.mode not in ("prompt", "plan"):
        raise HTTPException(400, "mode must be 'prompt' or 'plan'")

    try:
        sections = await asyncio.to_thread(_opt_detect_sections, req.raw_input, req.mode)
    except Exception as e:
        raise HTTPException(500, f"Section detection failed: {e}") from e

    doc_id = str(uuid.uuid4())[:8]
    doc = {
        "id": doc_id,
        "mode": req.mode,
        "raw_input": req.raw_input,
        "sections": sections,
        "context": None,
    }
    opt_state["documents"][doc_id] = doc
    opt_state["versions"][doc_id] = []
    return doc


@app.get("/optimizer/docs")
async def opt_list_docs():
    return [
        {"id": d["id"], "mode": d["mode"], "section_count": len(d["sections"])}
        for d in opt_state["documents"].values()
    ]


@app.post("/optimizer/iterate")
async def opt_iterate(req: OptIterateRequest):
    doc = opt_state["documents"].get(req.doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    section = next((s for s in doc["sections"] if s["id"] == req.section_id), None)
    if not section:
        raise HTTPException(404, "Section not found")

    old_content = section["content"]
    full_doc = _opt_full_document(doc["sections"])
    chat_key = f"{req.doc_id}:{req.section_id}"
    chat_history = opt_state["chat"].get(chat_key, [])
    project_context = doc.get("context")

    try:
        iteration = await asyncio.to_thread(
            _opt_iterate_section,
            doc["mode"], section, full_doc, project_context, chat_history, req.message,
        )
    except Exception as e:
        raise HTTPException(500, f"Iteration failed: {e}") from e

    new_content = iteration["rewrittenContent"]
    changed = new_content != old_content

    if changed:
        section["history"].append({
            "timestamp": datetime.datetime.now().isoformat(),
            "userMessage": req.message,
            "oldContent": old_content,
            "newContent": new_content,
            "reasoning": iteration["reasoning"],
        })
        section["content"] = new_content

    # Update chat history for this section
    chat_history = chat_history + [
        {"role": "user", "text": req.message},
        {"role": "assistant", "text": iteration["reasoning"]},
    ]
    opt_state["chat"][chat_key] = chat_history

    # Compute diff
    diff = diff_lines(old_content, new_content)

    # Detect conflicts (non-blocking — errors here are swallowed)
    conflicts: list[dict] = []
    if changed:
        try:
            conflicts = await asyncio.to_thread(
                _opt_detect_conflicts, doc["sections"], req.section_id, project_context,
            )
        except Exception as ce:
            logging.getLogger(__name__).warning("Conflict detection failed: %s", ce)

    return {
        "section": section,
        "diff": diff,
        "conflicts": conflicts,
        "reasoning": iteration["reasoning"],
        "clarifyingQuestion": iteration["clarifyingQuestion"],
        "suggestedContextUpdate": iteration["suggestedContextUpdate"],
        "changed": changed,
    }


@app.get("/optimizer/history/{doc_id}")
async def opt_history(doc_id: str):
    versions = opt_state["versions"].get(doc_id)
    if versions is None:
        raise HTTPException(404, "Document not found")
    return versions


@app.post("/optimizer/snapshot/{doc_id}")
async def opt_snapshot(doc_id: str):
    doc = opt_state["documents"].get(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    snapshot = {
        "timestamp": datetime.datetime.now().isoformat(),
        "sections_snapshot": [
            {k: v for k, v in s.items() if k != "history"}
            for s in doc["sections"]
        ],
        "conflicts": [],
    }
    opt_state["versions"][doc_id].append(snapshot)
    return {"index": len(opt_state["versions"][doc_id]) - 1, "timestamp": snapshot["timestamp"]}


@app.post("/optimizer/revert/{doc_id}/{version_idx}")
async def opt_revert(doc_id: str, version_idx: int):
    doc = opt_state["documents"].get(doc_id)
    versions = opt_state["versions"].get(doc_id, [])
    if not doc:
        raise HTTPException(404, "Document not found")
    if version_idx < 0 or version_idx >= len(versions):
        raise HTTPException(400, "Invalid version index")
    snapshot = versions[version_idx]
    restored = []
    for snap_sec in snapshot["sections_snapshot"]:
        orig = next((s for s in doc["sections"] if s["id"] == snap_sec["id"]), None)
        restored.append({**snap_sec, "history": orig["history"] if orig else []})
    doc["sections"] = restored
    return {"sections": doc["sections"]}


@app.post("/optimizer/set_context")
async def opt_set_context(req: OptContextRequest):
    doc = opt_state["documents"].get(req.doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    try:
        extracted = await asyncio.to_thread(
            _call_claude_json, _PROMPT_CONTEXT_EXTRACTOR, req.context_text, 1500,
        )
        doc["context"] = extracted
    except Exception as e:
        raise HTTPException(500, f"Context extraction failed: {e}") from e
    return {"context": doc["context"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
