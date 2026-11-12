# Version: V2
import os
import asyncio
import datetime
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from planner import run_agent_loop, build_system_messages
from apple_calendar import get_today_events
from scan import run_daily_scan
from memory import load_memory_context, save_session
from models import ChatRequest, QueueStatusResponse, QueueStatusItem
import queue_manager
from executor.queue_watcher import QueueWatcher
from optimizer import optimizer_router

load_dotenv()

CALENDAR_NAME = os.getenv("APPLE_CALENDAR_NAME", "Calendar")
REMINDER_LIST = os.getenv("APPLE_REMINDER_LIST", "Work Tracker")

BASE_DIR = Path(__file__).parent

# ── Session state ─────────────────────────────────────────────────────────────

session: dict = {
    "messages": [{"role": "ai", "content": "Hi! What's on your mind?"}],
    "pending_actions": [],         # write tool calls awaiting confirmation (from agent loop)
    "pending_assistant_msg": None,
    "session_start_time": datetime.datetime.now(),
    "memory_context": "",
}

_watcher: QueueWatcher | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_today_calendar_context() -> str:
    try:
        events = get_today_events(CALENDAR_NAME)
        if not events:
            return "No events scheduled for today."
        lines = []
        for e in events:
            if e.get("allday"):
                lines.append(f"- {e['title']} (all day)")
            else:
                lines.append(f"- {e['title']} ({e['start']}–{e.get('end', '')})")
        return "\n".join(lines)
    except Exception:
        return ""


def _build_oai_messages() -> list[dict]:
    today = datetime.date.today().isoformat()
    calendar_context = _get_today_calendar_context()
    system_msgs = build_system_messages(today, session["memory_context"], calendar_context)
    oai = list(system_msgs)
    for m in session["messages"]:
        role = "user" if m["role"] == "user" else "assistant"
        oai.append({"role": role, "content": m["content"]})
    return oai


def _actions_to_frontend(actions: list) -> list[dict]:
    return [{"tool": a["name"], **a["args"]} for a in actions]


def _label_for_item(raw: dict) -> str:
    t = raw.get("type", "")
    if t == "create_event":
        return f"Create event: {raw.get('title')} on {raw.get('date')}"
    if t == "create_reminder":
        return f"Reminder: {raw.get('title')} due {raw.get('date')} at {raw.get('time')}"
    if t == "move_event":
        return f"Move '{raw.get('original_title')}' → {raw.get('new_date')} {raw.get('new_start')}"
    if t == "edit_event":
        return f"Edit event: {raw.get('title')} on {raw.get('date')}"
    if t == "update_reminder_date":
        return f"Reschedule '{raw.get('title')}' → {raw.get('new_date')}"
    if t == "edit_reminder":
        return f"Edit reminder: {raw.get('title')}"
    if t == "delete_event":
        return f"Delete event: {raw.get('title')} on {raw.get('date')}"
    if t == "delete_reminder":
        return f"Delete reminder: {raw.get('title')}"
    return raw.get("id", "unknown")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _watcher
    session["memory_context"] = load_memory_context()

    # Start executor watcher as daemon thread (not a fork — safe on macOS)
    _watcher = QueueWatcher()
    watcher_thread = threading.Thread(target=_watcher.start, daemon=True)
    watcher_thread.start()

    yield

    if _watcher:
        _watcher.stop()

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


app = FastAPI(lifespan=lifespan)
app.include_router(optimizer_router)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


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


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(req: ChatRequest):
    session["messages"].append({"role": "user", "content": req.message})
    oai_messages = _build_oai_messages()

    result = await asyncio.to_thread(
        run_agent_loop, oai_messages, CALENDAR_NAME, REMINDER_LIST,
    )

    reply = result["reply"] or ""
    pending = result["pending_actions"]

    if pending:
        session["pending_actions"] = pending
        session["pending_assistant_msg"] = result["assistant_msg"]

    session["messages"].append({"role": "ai", "content": reply})
    return {
        "reply": reply,
        "actions": _actions_to_frontend(pending) if pending else None,
        "confirm": bool(pending),
    }


# ── Confirm / Cancel ──────────────────────────────────────────────────────────

@app.post("/confirm_action")
async def confirm_action():
    pending = session.get("pending_actions", [])
    if not pending:
        return {"reply": "No pending actions to confirm.", "actions": None, "confirm": False}

    # Flip all proposed queue items to confirmed — triggers the watcher
    confirmed_ids = await asyncio.to_thread(queue_manager.confirm_all_proposed)

    session["pending_actions"] = []
    session["pending_assistant_msg"] = None

    if confirmed_ids:
        id_list = ", ".join(confirmed_ids)
        reply = f"Confirmed {len(confirmed_ids)} action(s) ({id_list}). Executing in background — check status below."
    else:
        reply = "Nothing in queue to confirm."

    session["messages"].append({"role": "ai", "content": reply})
    return {"reply": reply, "actions": None, "confirm": False}


@app.post("/cancel_action")
async def cancel_action():
    removed_ids = await asyncio.to_thread(queue_manager.remove_proposed)
    session["pending_actions"] = []
    session["pending_assistant_msg"] = None
    reply = "Cancelled — no changes made."
    if removed_ids:
        reply = f"Cancelled {len(removed_ids)} action(s) — nothing written to Calendar or Reminders."
    session["messages"].append({"role": "ai", "content": reply})
    return {"reply": reply, "actions": None, "confirm": False}


# ── Queue status (frontend polls this after confirm) ──────────────────────────

@app.get("/queue_status", response_model=QueueStatusResponse)
async def queue_status():
    all_items = await asyncio.to_thread(queue_manager.list_all)

    # Only surface items that are in-flight or settled (not old done items from previous sessions)
    relevant = [i for i in all_items if i.get("status") in ("confirmed", "done", "failed")]

    status_items = [
        QueueStatusItem(
            id=i["id"],
            type=i.get("type", ""),
            status=i["status"],
            title=_label_for_item(i),
            error=i.get("error"),
        )
        for i in relevant
    ]

    return QueueStatusResponse(
        items=status_items,
        pending_count=sum(1 for i in status_items if i.status == "confirmed"),
        done_count=sum(1 for i in status_items if i.status == "done"),
        failed_count=sum(1 for i in status_items if i.status == "failed"),
    )


# ── Daily scan ────────────────────────────────────────────────────────────────

@app.post("/daily")
async def daily():
    try:
        result = await asyncio.to_thread(
            run_daily_scan, CALENDAR_NAME, REMINDER_LIST, session["memory_context"],
        )
    except Exception as e:
        result = {"reply": f"Daily scan failed: {str(e)}", "pending_actions": [], "assistant_msg": None}

    reply = result["reply"] or "Nothing to report."
    pending = result.get("pending_actions", [])

    if pending:
        session["pending_actions"] = pending
        session["pending_assistant_msg"] = result.get("assistant_msg")

    session["messages"].append({"role": "ai", "content": reply})
    return {
        "reply": reply,
        "actions": _actions_to_frontend(pending) if pending else None,
        "confirm": bool(pending),
    }


# ── New session ───────────────────────────────────────────────────────────────

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
    session.update({
        "messages": [{"role": "ai", "content": "Hi! What's on your mind?"}],
        "pending_actions": [],
        "pending_assistant_msg": None,
        "session_start_time": datetime.datetime.now(),
        "memory_context": load_memory_context(),
    })
    return {"reply": "Session saved. Starting fresh!", "actions": None, "confirm": False}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
