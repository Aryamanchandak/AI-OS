import os
import json
import asyncio
import datetime
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Fix imports: app.py was moved to top-level but modules live one level down
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

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Mount the UPI ledger dashboard under /upi if the brain layer is available.
if _UPI_DASHBOARD_OK and upi_app is not None:
    app.mount("/upi", upi_app, name="upi")


@app.get("/")
async def root():
    return FileResponse(str(_STATIC_DIR / "index.html"))


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
