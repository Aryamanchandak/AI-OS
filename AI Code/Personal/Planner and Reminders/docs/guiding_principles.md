# Planning Assistant — Product Vision

**Last updated:** 2026-04-10  
**Interface:** Streamlit (later: WhatsApp)  
**Calendar target:** Apple Calendar + Apple Reminders (via AppleScript, local macOS)  
**LLM Backend:** OpenAI API (GPT-4o)

---

## Core Idea

A chat interface that behaves like a smart collaborator, not a command executor. It listens, probes, builds context — and only moves to action when a real task has crystallised. Between "understanding what you want" and "doing it" is an explicit planning phase that you can see, interrogate, and edit. Nothing touches your calendar without your confirmation.

---

## The Three Modes

### Mode 1 — Chat
- Casual, open-ended conversation
- Bot does NOT try to extract tasks from everything — a "hi" is just a hi
- Responds naturally: asks follow-up questions, expands on what you've said, builds context across turns
- Full message history passed to OpenAI on every call
- **Forward transition:** a concrete actionable task or plan crystallises — bot asks: *"Okay, I think I have something to work with — want me to plan this out?"*
- **No automatic transition** — bot always asks permission before shifting to planning mode

### Mode 2 — Planning (Surfaced)
- Explicitly visible — not a background step
- Bot proposes a structured breakdown: events to create, reminders to set, follow-ups to track
- Rendered as a **planning card** inline in the chat (not a modal, not a separate screen)
- **"Walk me through this"** → bot narrates the full plan as a single explanation block: what it understood per item, what it assumed, and why — e.g. *"I set Tuesday because you said early next week, and defaulted to 10am based on your past preferences"*
- **Editing happens via chat**, not inline on the card — you say *"change the Raj meeting to Thursday"* and the bot updates the plan and re-renders the card
- **"Go ahead"** → confirm and move to implementation. Nothing is written before this.
- **Backward transition:** if you say *"actually not yet"* or *"let's keep talking"*, the bot returns to chat mode and the draft plan is preserved in session state but not shown until you re-engage it

### Mode 3 — Implementation
- Takes the confirmed plan JSON and writes to Apple Calendar / Reminders via AppleScript
- Shows a line-by-line summary of what was created, with any errors surfaced conversationally
- Returns to Mode 1 (chat) after execution — the session continues, it does not close

---

## State Machine (explicit)

```
         [casual message]
CHAT ─────────────────────────────────────────► CHAT
  │                                               ▲
  │ [task crystallises + user says yes]           │ [user says "not yet" / "keep talking"]
  ▼                                               │
PLANNING ◄─────────────────────────────────────────
  │
  │ [user says "go ahead"]
  ▼
IMPLEMENTATION ──► [writes to calendar] ──► CHAT
```

State is stored in `st.session_state.mode`. Any unrecognised signal stays in current mode — never auto-advances.

---

## Key Behavioural Principles

- **Don't hallucinate a plan from a casual message.** A "hi" is just a hi.
- **Withhold commitment.** If date/time/context is missing, ask — don't assume.
- **One clarifying question at a time.**
- **Always ask before shifting modes** — never auto-transition to planning.
- **Edits via chat, not UI controls** — keeps the interaction model simple and consistent.
- **Summarise before acting.** Always show the plan card before writing anything.
- **Backward transitions are valid** — returning to chat from planning is a first-class action.

---

## Structured Plan Schema

Used as the output format for Mode 2 and as input to Mode 3 writes. Also used for daily scan reshuffle proposals.

```json
{
  "events": [
    {
      "id": "evt_001",
      "title": "",
      "date": "YYYY-MM-DD",
      "time": "HH:MM",
      "duration_mins": 60,
      "calendar": "default",
      "notes": ""
    }
  ],
  "reminders": [
    {
      "id": "rem_001",
      "title": "",
      "due_date": "YYYY-MM-DD",
      "due_time": "HH:MM",
      "priority": "high|medium|low",
      "list": "Reminders"
    }
  ],
  "follow_ups": [
    {
      "id": "fu_001",
      "person": "",
      "topic": "",
      "by_when": "YYYY-MM-DD"
    }
  ]
}
```

IDs (`evt_001`, `rem_001`) are assigned at plan creation and used for targeted edits — e.g. *"change evt_001 to Thursday"* maps cleanly without ambiguity.

---

## Architecture

```
Streamlit UI
    ↓
st.session_state
  - messages: full conversation history
  - mode: chat | planning | implementation
  - current_plan: structured JSON (populated in planning mode)
  - memory_context: loaded from /memory on session start
    ↓
OpenAI API  (chat.completions.create, gpt-4o)
  - system prompt varies by mode
  - Mode 1: collaborative listener, task detector, signals with <mode:planning>
  - Mode 2: structured JSON planner + walkthrough narrator
  - Mode 3: not an LLM call — pure Python + AppleScript execution
    ↓
Response router
  - detects <mode:planning> tag → flip mode, render plan card
  - detects user confirmation → trigger AppleScript writes
  - detects backward signal → return to chat, preserve draft plan
  - else → render chat message, stay in current mode
    ↓
AppleScript layer  (subprocess.run, synchronous, no threading)
  - read_reminders.applescript → JSON
  - read_calendar.applescript → JSON
  - write_event.applescript(event_json) → success/error
  - write_reminder.applescript(reminder_json) → success/error
  - update_reminder_date.applescript(id, new_date) → success/error
```

---

## Error Handling

Every failure must be caught and returned as a conversational message — never a silent fail or a raw Python traceback.

| Failure | Handling |
|---|---|
| OpenAI timeout / rate limit | Retry once with backoff, then surface: *"Having trouble reaching OpenAI — want to try again?"* |
| Malformed JSON from model | Re-prompt once with the raw output and instruction to fix format; if still broken, surface: *"I had trouble structuring that plan — can you restate what you'd like?"* |
| AppleScript write fails | Capture stderr, surface per-item: *"I created the calendar event but couldn't set the Raj reminder — error: [msg]. Want me to try again?"* |
| AppleScript read returns empty | Surface: *"I couldn't read your calendar — make sure Automation permissions are granted in System Settings."* |
| Memory file unreadable | Skip that file, log warning, continue — don't crash session startup |
| Backward mode transition | Preserve `current_plan` in session state, clear the rendered card, return to chat |

---

## Persistent Memory — Markdown Conversation Logs

Every session is saved as a markdown file in `/memory/`. Future sessions load recent logs for continuity — no database needed.

### File naming
```
/memory/YYYY-MM-DD_HH-MM_<auto-title>.md
```
Auto-title is 3–5 words generated by the model at session end — e.g. `2026-04-10_14-32_investor-deck-prep.md`. Makes the folder browsable by topic, not just date.

### File format
```markdown
# Session: 2026-04-10 14:32
# Title: investor deck prep
## Modes visited: chat → planning → implemented

### Conversation
**You:** ...
**Bot:** ...

### Plan Executed
[confirmed JSON]

### Carry-Forward Notes
- Follow-up with Raj scheduled for Thursday — not yet confirmed complete
- User prefers morning slots for deep work
- [anything worth remembering next session]
```

### Memory loading strategy on session start
Load in this priority order until ~2000 token budget is reached:
1. **Carry-Forward Notes** from all sessions in the last 7 days (most compact, highest signal)
2. **Full conversation** from the most recent session only
3. Nothing older — old files stay on disk but are not loaded unless explicitly requested

Bot opens with a brief acknowledgement of what it remembers — not a wall of text.

### Pruning
Files are never auto-deleted. The loading strategy naturally ignores old files. User can manually archive if the folder grows large — the app won't break.

---

## Daily Agent Scan

Triggered manually via a **"Run Daily Check"** button in the Streamlit sidebar. No scheduled trigger — press it when you're ready to triage.

### What it scans
1. **Apple Reminders** — all incomplete todos with due dates
2. **Apple Calendar** — all events for the next 7 days

### Pre-analysis (Python, before model call)
Python does the objective arithmetic so the model focuses on reasoning, not date math:
- Sort events by start time, flag overlapping pairs
- Flag reminders where `due_date < today` and status is incomplete (missed todos)
- Flag reminders with no due date sitting for more than 7 days (orphaned todos)
- Count events per day, flag any day exceeding a threshold (default: 4 events)

Structured pre-analysis is sent to the model alongside the raw dump.

### Three sub-problems — tested and handled independently
1. **Missed todos** — due date passed, still incomplete → model proposes a new due date
2. **Calendar conflicts** — overlapping events → model proposes which to move and when, with reasoning
3. **Overloaded days / orphaned todos** — surfaced for review, no auto-action proposed

### Output
- Conversational morning briefing appears as the opening chat message
- Reshuffle proposal renders as a planning card (same schema, same confirm flow as Mode 2)
- Nothing is moved or created without user confirmation

---

## UI Layout (Streamlit)

- **Main area:** chat window — all three modes feel like one continuous conversation
- **Sidebar:** mode indicator (Chat / Planning / Confirmed), "Run Daily Check" button, "New Session" button
- **Planning card:** rendered inline in chat as a styled `st.container` — not a modal
- **Session saves** on "New Session" button click (write to `/memory/` then reset state)

---

## Backend & Technical Constraints

### LLM
- OpenAI API, `gpt-4o`
- `openai` Python SDK, `chat.completions.create`
- Full message history sent every call
- Structured JSON in planning mode via `response_format: {"type": "json_object"}` with schema in system prompt
- Mode signals via tags in text: `<mode:planning>`, `<mode:chat>`

### Mac / Python Constraints
- **No `multiprocessing` with fork().** macOS + Python + OpenAI SDK crashes with the fork() issue. Use `threading` or `asyncio` only. If multiprocessing is ever needed, set `multiprocessing.set_start_method('spawn')` at the very top of the entry point before any imports.
- **No background threads writing to `st.*`** — Streamlit is not thread-safe for UI updates. All UI writes in the main thread only.
- **AppleScript via `subprocess.run(['osascript', '-e', script], capture_output=True, text=True)`** — synchronous and safe. Always check both `stdout` and `stderr`. AppleScript errors go to stderr.
- **No launchd / cron / background processes** — all triggers are manual buttons.
- **Permissions:** first run requires granting Automation permissions to Terminal / Python in System Settings → Privacy & Security → Automation. If AppleScript returns a permissions error, surface it clearly with instructions.

---

## Build Breakdown

Each phase is independently testable. Complete and verify before starting the next. Hand this doc to Claude Code at the start of every session.

### Phase 1 — Baseline OpenAI chat in Streamlit
Streamlit chat UI: `st.chat_input`, `st.chat_message`, messages in `st.session_state.messages`. Full history passed to `gpt-4o` every turn. System prompt hardcoded. No modes, no memory, no calendar. Goal: working multi-turn chat that preserves history across reruns.

### Phase 2 — Mode state machine
Add `st.session_state.mode` (`chat | planning | implementation`). Three distinct system prompts. Parser detects `<mode:planning>` in response and flips mode. Implement backward transition: "not yet" / "keep talking" returns to chat and preserves `st.session_state.current_plan`. Test all transitions including edge cases. Casual messages must never auto-trigger planning.

### Phase 3 — Planning card UI + chat-based editing
In planning mode, model outputs JSON alongside its message. Render as a clean planning card (`st.container`). Add "Walk me through this" and "Go ahead" buttons. Edits via chat — user types a change, bot updates JSON, card re-renders. "Go ahead" prints confirmed JSON to console for now. Test the edit-and-re-render loop thoroughly.

### Phase 4 — Markdown memory: write
On "New Session" button, write `/memory/YYYY-MM-DD_HH-MM_<title>.md`. Title from model (3–5 word summary). File includes full conversation, confirmed plan JSON, and carry-forward notes from the model. Verify files are written correctly and notes are meaningful.

### Phase 5 — Markdown memory: read + inject
On session start, scan `/memory/`, load carry-forward notes from last 7 days + most recent full conversation, cap at ~2000 tokens. Inject as system-level context block before first user message. Verify bot references prior sessions naturally.

### Phase 6 — AppleScript read layer
Write `read_reminders.applescript` and `read_calendar.applescript`. Both output JSON arrays. Call from Python via `subprocess.run`. Parse output. "Run Daily Check" button triggers both scripts and displays raw JSON in the UI for verification. No model call yet — just confirm the read layer works.

### Phase 7 — Daily scan pre-analysis + model briefing
Take Phase 6 JSON, run Python pre-analysis (overlaps, missed todos, orphaned todos, overloaded days). Send structured pre-analysis + raw data to model with scan system prompt. Model returns briefing + reshuffle proposal JSON. Briefing as opening chat message, proposal as planning card. Same confirm flow as Phase 3. No writes yet.

### Phase 8 — AppleScript write layer
Write `write_event.applescript`, `write_reminder.applescript`, `update_reminder_date.applescript`. Wrap in Python functions with full error handling — capture stderr, return structured success/error dict. Wire "Go ahead" (Phase 3) to write functions. Wire daily scan confirm (Phase 7) to update functions. Surface all errors conversationally. Test each write script independently before wiring.

---

## Future
- Replace Streamlit with WhatsApp (same Python backend, swap I/O layer)
- Add Slack / email for follow-up tracking
- Session search: query `/memory/` folder by topic keyword