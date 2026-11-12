# Planner and Reminders — Codebase Overview

**Last updated:** 2026-06-14

---

## 1. What This Project Is

This is a personal AI planning assistant that lives in a web browser on your Mac and talks directly to your Apple Calendar and Apple Reminders. You have a natural conversation with it — "remind me to send Raj the deck tomorrow at 9am", "move my 2pm standup to Thursday" — and it takes care of creating, rescheduling, or deleting entries in your actual calendar and reminders apps. Nothing touches those apps without you explicitly approving it first. The system also has a spending awareness layer: you can ask it questions about your UPI payment history, and it will look them up from a local database alongside your scheduling queries.

---

## 2. The Big Picture — How It All Fits Together

Imagine the system as three distinct rooms connected by a hallway, with a locked door in the middle.

The first room is the **chat interface** — a dark, minimal webpage that feels like a conversation. You type here, and a language model (OpenAI's GPT-4o) reads your message, thinks about your calendar and your question, and responds in plain English.

The locked door in the middle is the **action queue** — a plain text file called `queue.md` that lives at the project root. When the AI decides something needs to be added to your calendar, it doesn't do it immediately. Instead, it writes a careful, structured description of the proposed action into this file and shows you a confirmation card on screen. The action sits there, marked "proposed", waiting for your approval.

When you click Confirm, the status in that file flips to "confirmed", and a background watcher that has been sitting quietly the whole time immediately notices. This watcher lives in the second room: the **executor**. The executor's job is to take confirmed items from the queue and actually carry them out, by calling a third piece of the system.

That third piece is the **MCP server** — a small, independent subprocess that the executor spawns on demand. MCP stands for Model Context Protocol, which is a standard way for AI tools to expose capabilities. This server wraps the actual macOS automation layer: it sends AppleScript commands to Apple Calendar and Apple Reminders to create, edit, move, or delete items. When it finishes, it reports success or failure back to the executor, which writes the outcome back into `queue.md`. The frontend polls that file's status and shows you a completion message — or an error — in the chat.

Reading your calendar and reminders (as opposed to changing them) follows a faster, simpler path: the AI calls those directly via AppleScript, with no queue and no confirmation needed, because reading is always safe.

There is also a persistent memory layer: every session is saved as a markdown file in your Obsidian vault. Future sessions load the most recent carry-forward notes from those files so the assistant remembers what you discussed before.

---

## 3. Every Component — What It Does and Why It Exists

### The Frontend and Web Server (app.py, static/index.html)

The web server is built with FastAPI and serves a single-page HTML application. When you open the app in a browser, the page loads and immediately fetches the current session state — whatever messages were exchanged, and whether there is a pending action card waiting for you. The visual design is a dark terminal-style interface with animated colour blobs in the background, a narrow central chat column, and a fixed action card area below the conversation.

The server manages a single in-memory session object containing the conversation history, any pending write actions, and the loaded memory context. It exposes a handful of endpoints: one for chat messages, one to confirm pending actions, one to cancel them, one for the daily check feature, one to query the current state of the queue (for polling after confirmation), and one to start a new session.

When the server starts up, it loads recent memory from disk, then launches the queue watcher as a background daemon thread. When the server shuts down — or when you click "New Session" — it saves the current conversation to disk as a dated markdown file.

The frontend renders messages with a minimal markdown parser (bold, italic, code spans, headers). Assistant messages get the full markdown treatment; your messages are shown as plain text.

### The AI Agent Loop (planner.py)

This is the brain of the system. When you send a message, the server calls the agent loop and hands it the full conversation history plus two system prompts: one describing today's calendar context and the AI's behavioural rules, and one containing carry-forward memory from your recent sessions.

The agent loop sends this to GPT-4o and waits for a response. The model can either respond with plain text (ending the loop), or it can call one of sixteen tools. The tools split into two categories:

Read tools are executed immediately and automatically. When the model calls `check_calendar` or `check_reminders`, the result comes back in under a second via AppleScript, gets appended to the conversation, and the model continues reasoning. Multiple read tools can run in parallel — if the model asks for both your calendar and your reminders at the same time, both fetch happen simultaneously. The five UPI spending tools (which query a local SQLite database) also fall into this read-only category.

Write tools are never executed immediately. When the model calls `create_event` or `move_event` or any of the eight write/edit/delete tools, the agent loop validates the arguments through a strict data model, writes the item to `queue.md` with status "proposed", and returns to the frontend carrying the list of proposed actions. The loop stops and waits. No action has been taken yet.

If the model hits a maximum of eight loop iterations without producing a text response, it gets a final instruction to summarise what it actually knows — and critically, not to describe actions it didn't actually take.

The loop also contains two legacy functions — `edit_plan` and `walkthrough` — which remain from the original planning mode but are not used in the current conversational flow.

### The Data Models (models.py)

Every piece of data that crosses a boundary in this system is described by a strict typed model. These models serve as a contract: if the AI tries to create a reminder without a time, it fails right here, before anything is written to the queue. If the executor reads a malformed item from the queue, it fails right here, before anything touches AppleScript.

There are models for things that can be read from the calendar (events, reminders), models for every type of queue item (eight in total: create event, create reminder, move event, edit event, update reminder date, edit reminder, delete event, delete reminder), and models for the FastAPI request and response bodies. The queue item models share a common base that carries the item's ID, its lifecycle status (proposed, confirmed, done, or failed), and timestamps for each stage.

The eight queue item types are combined into a single "union" type — a structure that says "this could be any of these eight things" and uses the `type` field to determine which. This is used when reading items back from the queue, so parsing a JSON block always produces the correct specific model.

### The Queue Manager (queue_manager.py)

This is the librarian for `queue.md`. It knows how to read all the JSON blocks from the file, write them back, append new items, flip "proposed" items to "confirmed", remove cancelled items, and update individual item statuses after execution.

Because both the web server and the executor can write to this file at the same time, every write operation acquires an exclusive file lock before touching the file. This prevents corruption when the executor marks an item as "done" at the same moment the user is cancelling something else.

IDs are generated sequentially by scanning the existing file for the highest-numbered ID with each prefix: `evt_NNN` for new events, `rem_NNN` for new reminders, and `act_NNN` for everything else (moves, edits, deletes).

### The Queue Watcher (executor/queue_watcher.py)

This is a small background thread that watches `queue.md` for changes using macOS's native filesystem events mechanism. Every time the file is modified, it waits half a second (to absorb any rapid consecutive writes), then checks whether there are any items with "confirmed" status. If there are, it calls the executor. If there are not — for example, the executor itself just wrote "done" back to the file — it does nothing. This self-trigger guard prevents the watcher from creating an infinite loop.

### The Executor (executor/executor.py)

The executor is triggered by the watcher and does the actual work of carrying out confirmed queue items. It reads all "confirmed" items from the queue, validates each one through the strict data models, then spawns the MCP server as a subprocess and connects to it over a standard input/output channel.

It works through the confirmed items one at a time. For each item, it translates the structured data model into the appropriate MCP tool call — for example, a `MoveEventItem` becomes a call to the MCP server's `move_event` tool with the original title, original date, and new date and time as arguments. After each call, it checks whether the response signals success or an error (error responses start with "ERROR:"), and writes the outcome back to the queue.

The MCP server subprocess lives only as long as it takes to process the batch. It is not a persistent background process.

### The MCP Server (mcp_server/applescript_mcp.py)

This is the bridge between the queue-based execution layer and macOS. It runs as a short-lived subprocess and exposes ten tools across three categories: two read tools that return calendar events and reminders, two create tools for new events and reminders, and six edit tools for moving events, editing events, rescheduling reminders, editing reminder content, and deleting either.

Each tool call validates its arguments (using the same data models as the rest of the system), then calls the appropriate AppleScript function. If anything goes wrong — a calendar name that doesn't exist, an event that can't be found — the error is caught and returned as a response prefixed with "ERROR:" so the executor knows to mark the item as failed.

The MCP server also re-validates its inputs before calling AppleScript, meaning the data has been checked at least twice by the time it reaches the macOS layer.

### The AppleScript Layer (apple_calendar.py, apple_reminders.py)

These two files contain the actual macOS automation. They use a technique called NSTask (via the PyObjC bridge to macOS's Objective-C APIs) to run the `osascript` interpreter in a subprocess. This is significant: it avoids the `fork()` system call that crashes on macOS when used alongside certain Python libraries. Every AppleScript execution is thread-safe.

The functions cover: creating timed and all-day calendar events, moving events to new times, editing event properties, deleting events, reading today's events, reading the next seven days of events, creating reminders with due dates and timed alerts, listing open reminders from one list or all lists, rescheduling reminders, editing reminder content, deleting reminders, and marking reminders complete.

Event and reminder lookup by title works by scanning all items on the given date and matching by exact title string. This means if two events have the same title on the same day, only the first match is affected — a known limitation.

### The Memory System (memory.py)

At the end of each session, the conversation is saved to a markdown file in an Obsidian vault directory. A small language model (GPT-4o-mini) generates two things: a three-to-five-word slug for the filename (making the folder browsable by topic), and a set of bullet-point carry-forward notes capturing unresolved commitments, stated preferences, and any feedback about how plans played out.

At the start of each session, the memory loader reads markdown files from the last seven days, extracts just the carry-forward notes sections, and assembles them into a compact context block. It also includes the full conversation from the single most recent session. The whole thing is capped at roughly eight thousand characters so it doesn't overwhelm the system prompt. If no memory files exist, nothing breaks — the session simply starts without context.

### The Daily Scan (scan.py)

Triggered by the "daily check" button in the topbar, this runs a structured analysis before handing off to the AI. Python does the mechanical date arithmetic first: it identifies reminders whose due dates have already passed (missed todos), reminders with no due date that have been sitting for more than a week (orphaned todos), calendar events that overlap each other on the same day (conflicts), and days that have more than four events (overloaded days).

This pre-analysis is bundled with the raw calendar and reminder data and sent to the agent loop as a user message. The AI then provides a morning briefing and, for missed todos and calendar conflicts, calls the write tools to propose fixes using the same confirmation flow as normal chat.

### The UPI Spending Tools (upi_tools.py)

Five read-only functions that query a SQLite database at a fixed path in the user's home directory. The database is populated by a separate "brain" system (not part of this codebase). The functions cover: total spending today, spending by category over a configurable window, recent payment history, top recipients by total spend, and the status of any active spending goals. If the database doesn't exist, each function returns a friendly message explaining how to set it up. These are exposed as agent tools and called directly when the user asks spending-related questions.

---

## 4. How a Typical Interaction Works

You open the browser, the chat interface loads, and you see the greeting message. You type: "I need to prep for my investor pitch on Friday — can you help me plan the week?"

The message goes to the server, which assembles the full conversation history including today's calendar context (injected automatically from a live AppleScript read at every request) and any carry-forward memory from the past week. The agent loop sends all of this to GPT-4o.

The model decides it needs to check your calendar before proposing anything. It calls `check_calendar` with a seven-day window. The system runs the AppleScript, gets back a list of your events for the week, appends the results to the conversation, and the model runs again with this new information.

Now informed, the model sees you have a free morning on Wednesday and a gap Thursday afternoon. It proposes three things: a two-hour prep block on Wednesday morning, a reminder to finalise the deck slides on Thursday at 9am, and a reminder to confirm the meeting room on Friday morning at 8am. It calls `create_event` and `create_reminder` three times.

Instead of executing those calls, the agent loop validates each one through the data models — catching any missing required fields like a missing time for the reminder — and writes three "proposed" entries to `queue.md`. It sends back a text reply explaining what it wants to do, alongside the confirmation card listing all three actions.

The mode badge in the topbar changes to "confirm". You see the card. It looks right. You click Confirm.

The server calls `confirm_all_proposed()`, which flips all three items from "proposed" to "confirmed" in `queue.md`. The queue watcher detects the file change within half a second. It checks for confirmed items, finds three, and calls the executor.

The executor spawns the MCP server subprocess, connects to it, and processes the three items in sequence. Each one triggers an AppleScript command to Apple Calendar or Apple Reminders. On success, each item's status flips to "done". The executor finishes, the MCP subprocess exits.

Meanwhile, the frontend has started polling the `/queue_status` endpoint every two seconds. It sees the items transition from "confirmed" to "done", stops polling, and appends a message to the chat: "Done: Create event: Pitch Prep Block on 2026-06-18, Reminder: Finalise deck slides..."

The whole cycle from your message to confirmed execution typically takes ten to fifteen seconds — the AI conversation is the longest part; the actual calendar writes take a second or two once confirmed.

---

## 5. How the System Makes Decisions

The model's first decision on every message is whether to call any tools at all. The system prompt tells it explicitly that a casual greeting or non-schedule question should receive a plain text reply. Only when the message is schedule-related should tools be considered.

When the model decides to read data, it chooses between `check_calendar` and `check_reminders` based on what kind of information is needed. For spending questions, it picks from the five UPI tools. These read decisions are entirely the model's judgment — there is no routing logic in the Python code; that responsibility sits with the AI.

When the model decides to propose a write action, the Python code enforces a hard rule: it stops the loop and waits for confirmation. There is no mechanism for the model to bypass this. A write tool call always produces a pending action card, never a direct execution.

The executor's decision about whether to act is simpler: it only processes items with "confirmed" status. If the queue has changed but all items are in "done", "failed", or "proposed" states, it immediately returns without doing anything. This is the self-trigger guard that prevents feedback loops.

For the MCP server, the decision on whether an operation succeeds or fails is determined by the AppleScript itself: if the script exits with a non-zero status, the error message is captured and returned. The server translates that into an "ERROR:" prefixed response, which the executor recognises as a failure.

The memory system makes a priority decision at load time: carry-forward notes from the past seven days take priority over full conversation text from older sessions, and the most recent session's full conversation is only included if there is budget remaining after notes.

---

## 6. How the Code Actually Flows — The Execution Journey

**Entry point:** The system starts with `uvicorn app:app --port 8000`. FastAPI's startup sequence runs the lifespan function, which loads memory from disk and launches the queue watcher as a background daemon thread. From this point, two things run concurrently: the web server handling HTTP requests, and the watcher watching `queue.md`.

**A message arrives:** The browser sends a POST to `/chat`. The handler appends the message to the session's conversation list, then calls `_build_oai_messages()` to assemble the full history. This function first calls AppleScript to read today's calendar events, combines that with today's date and the loaded memory context, builds the two system messages (behavioural rules + memory block), and prepends them to the conversation history. The result is a list of messages ready for the AI.

**The agent loop runs in a thread:** Because the OpenAI call would block the async web server, it runs in a thread pool via `asyncio.to_thread`. Inside the loop, GPT-4o receives the messages and responds. If it responds with plain text, the loop returns immediately. If it requests tool calls, the code separates them into reads and writes.

**Read tools execute in parallel:** If there are only read tool calls, a thread pool runs them all simultaneously. Each AppleScript read typically takes one to three seconds. The results are added to the message list as "tool result" messages, and the loop calls GPT-4o again with the enriched conversation.

**Write tools halt the loop:** The moment any write tool appears in a response, the loop collects the proposed actions, validates each one through Pydantic, writes them to `queue.md`, and returns to the web server with a "pending_actions" payload. The session stores these pending items. The web server sends them to the browser. The loop is done — it will not run again until the next `/chat` request.

**Confirmation triggers the watcher:** When the browser POSTs to `/confirm_action`, the queue manager acquires a file lock and flips all "proposed" items to "confirmed". The file is written and the lock released. The watchdog filesystem event fires within milliseconds. After a half-second debounce, the watcher checks for confirmed items and finds them.

**The executor runs:** In the watcher's callback thread, `run_execute_confirmed()` is called synchronously. This runs an asyncio event loop in the thread (using `asyncio.run`). Inside the async function, the MCP client library spawns the MCP server Python process as a subprocess over stdin/stdout. The client handshakes with the server, then calls tools one by one.

**The MCP server processes each call:** The MCP server (running as a separate process) receives the tool call over its standard input, validates the arguments using Pydantic models, dispatches to the appropriate AppleScript function, runs the script via NSTask, and returns the result over its standard output. For a `create_event` call, the AppleScript opens Apple Calendar and creates a new event. The MCP server responds with "Created event: [title] on [date]" or "ERROR: [message]".

**Statuses are updated:** Back in the executor, each response is checked. On success, `queue_manager.update_item_status(id, "done")` acquires the file lock and writes the updated status. On failure, "failed" is written along with the error text. The MCP subprocess stays alive for the whole batch, then exits when the `async with` context closes.

**The browser polls for results:** Every two seconds, the frontend checks `/queue_status`. The server reads `queue.md` and returns the current status of all relevant items. When the poll finds zero "confirmed" items and at least one "done" or "failed" item, polling stops and a completion message is rendered in the chat.

**Session end:** When the server shuts down or the user clicks "New Session", `save_session()` runs. It calls GPT-4o-mini twice — once to generate a filename slug, once to extract carry-forward notes — then writes the full markdown file to the Obsidian vault directory.

---

## 7. What the System Remembers

**During a session:** The session dictionary in memory holds the full conversation history (every user message and AI response as role-tagged text), any pending actions currently awaiting confirmation, and the memory context string loaded at startup. This is all in-process memory — it vanishes if the server process is killed without a clean shutdown.

**Between sessions:** The Obsidian vault directory holds one markdown file per session. Each file contains the full conversation, any confirmed plan JSON, and the carry-forward bullet points. These files are never deleted automatically. On each startup, the memory loader reads the carry-forward notes from files dated within the past seven days and the full conversation from the single most recent file, assembling a context string capped at roughly two thousand tokens. Older files sit on disk but are silently ignored.

**The action queue:** `queue.md` is persistent across restarts. Items that were "proposed" at shutdown will still be there when the server restarts, though the in-memory session state will have lost track of them. Items that were "confirmed" but not yet executed will be picked up and executed by the watcher when it starts — this is a useful property but could also be surprising if the server was shut down mid-confirmation.

**UPI data:** The spending data lives in a SQLite database at a fixed path in the home directory, managed by a separate system. This codebase only reads from it, never writes.

---

## 8. What the System Talks To

**OpenAI API:** The primary external dependency. GPT-4o is called for every user message and for each daily scan. GPT-4o-mini is called twice at session end (title generation and carry-forward note extraction). The system sends the full conversation history on every call, which means token costs grow with conversation length.

**Apple Calendar (via AppleScript):** Read and write access. The target calendar name is configurable via an environment variable, defaulting to "Calendar". Reads happen on every chat message (today's events injected into the system prompt) and when the model calls `check_calendar`. Writes happen via the MCP server when the executor processes confirmed items.

**Apple Reminders (via AppleScript):** Read and write access. The target list name is configurable via an environment variable, defaulting to "Work Tracker". The `list_all_open_reminders` function reads from every list, not just the configured default. Write operations go to the configured list unless the user specifies otherwise.

**The local filesystem:** Three locations matter: `queue.md` at the project root (the action queue), the Obsidian vault directory at a hardcoded absolute path in `memory.py` (session memory), and `~/.upi-agent/data.db` (the spending database). If the memory directory doesn't exist, it is created. If the database doesn't exist, spending tools return a friendly message rather than crashing.

**No network calls beyond OpenAI.** The calendar and reminder integrations are entirely local via AppleScript. There is no cloud sync, no webhook, no external service for scheduling or reminders.

---

## 9. What Is Currently Built vs. What Is Not Yet Built

**Fully working and complete:**

- The FastAPI web server and the static HTML chat interface
- The agent loop with GPT-4o function calling, including parallel read-tool execution
- The queue-based write flow: agent proposes, user confirms, executor carries out
- All eight queue item types (create event, create reminder, move event, edit event, update reminder date, edit reminder, delete event, delete reminder)
- The MCP server with all ten tools (two read, two create, six edit/delete)
- The AppleScript layer for all calendar and reminder operations, via NSTask
- The queue watcher using macOS filesystem events with debounce and self-trigger guard
- Pydantic V2 validation at all four described boundaries
- The file-locked queue manager
- The markdown memory system with carry-forward notes and token-budgeted loading
- The daily scan with Python pre-analysis and agent-loop integration
- The five UPI spending tools (read-only queries against local SQLite)

**Incomplete or partially built:**

- The "ledger" link in the topbar points to `/upi/` — there is no `/upi/` route in `app.py`. Clicking it would return a 404.
- The "share" and "archive" buttons in the topbar have no event handlers and do nothing.
- The model label in the topbar reads "gpt-5.4-nano" — this is clearly a placeholder display string that was never updated; the actual model configured in `planner.py` is `gpt-4o`.

**Referenced but not present in this codebase:**

- The UPI "brain" system that populates the SQLite database. The `upi_tools.py` file mentions a `brain.agent` module and references an iPhone-to-Mac SMS forwarding setup. None of this exists in the current project. The spending tools work correctly if the database is populated by that separate system, but without it they return a setup guidance message.
- WhatsApp integration. Mentioned in CLAUDE.md as a planned future replacement for the HTML frontend. No code exists for it.
- Session search across the memory folder by topic keyword. Mentioned in CLAUDE.md as a planned feature. Not implemented.

**Present in the repository but superseded:**

- The `Calendar and Reminders/` directory at the project root contains a copy of the core Python modules (`apple_calendar.py`, `apple_reminders.py`, `memory.py`, `planner.py`, `scan.py`, `upi_tools.py`) from an earlier version. These are not imported by anything in the current system and appear to be leftover artefacts from before the V2 refactor moved the files to the project root.

---

## 10. The Current State of the Project

This project is in a functionally complete state for its core purpose. The two-agent architecture described in `v2_plan.md` has been fully implemented: the code matches the plan, the boundaries are where they were designed to be, and the data flows as intended.

The strongest parts of the system are the data model layer and the queue flow. The decision to use Pydantic V2 with a discriminated union at every boundary means that malformed data from the AI is caught early, and the queue file is always in a consistent state. The file-locking design means concurrent writes from the web server and executor don't corrupt the queue. The self-trigger guard on the watcher is a thoughtful detail that prevents the system from spinning on its own status updates.

The most fragile part is the AppleScript event-matching logic. Events and reminders are looked up by exact title string match on a given date. This means rescheduling an event requires knowing its exact title — and if two events share a title on the same day, only the first is affected. This is a real limitation for a personal calendar with repeat meetings that share names. An error here produces a "failed" status on the queue item, which the user will see, but the mismatch won't be caught beforehand.

The hardcoded absolute path for the memory directory in `memory.py` is worth noting for anyone running this on a different machine — it will silently fail to read or write memory files without error, since the code catches all exceptions during memory operations.

For someone picking this up for the first time: start the server with `uvicorn app:app --port 8000` from the project root, make sure Apple Calendar and Apple Reminders automation permissions are granted to Terminal in System Settings, and set `OPENAI_API_KEY` in a `.env` file. The UPI features will gracefully degrade if the spending database isn't present.
