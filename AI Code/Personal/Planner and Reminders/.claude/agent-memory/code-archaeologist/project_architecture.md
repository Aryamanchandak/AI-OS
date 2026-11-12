---
name: App architecture — agentic function-calling (updated 2026-04-24)
description: FastAPI + static HTML frontend; OpenAI function-calling agent loop; no tag parsing; single-user module-level session dict
type: project
---

Architecture has been refactored from tag-parsing to OpenAI function calling. CLAUDE.md is now accurate. Key architecture facts:

- `app.py` — FastAPI server on port 8000, module-level `session` dict (single-user), endpoints: `/`, `/state`, `/chat`, `/confirm_action`, `/cancel_action`, `/daily`, `/new_session`. Pending state persisted to `pending_state.json` for crash recovery.
- `planner.py` — 7 tool schemas, `run_agent_loop` (LLM + auto-executes reads, pauses on writes), `execute_tool` dispatcher, `build_system_messages`. Also has legacy `edit_plan` and `walkthrough` (not wired to any endpoint).
- `apple_calendar.py` — creates/moves/deletes/reads events via NSTask+AppleScript
- `apple_reminders.py` — creates/updates/deletes/reads reminders via NSTask+AppleScript
- `scan.py` — daily scan: reads calendar+reminders, pre-analyses with pure Python, then calls `run_agent_loop`. Returns same shape as regular chat.
- `memory.py` — saves sessions to hardcoded Obsidian vault path (`/Users/aryamanchandak/Documents/Obsidian Vault/Aryamans Vault/Agent MD`). Loads carry-forward notes on startup.

The old mode state machine (chat/planning/implementation), `_DIRECT_KEYWORDS`, `_CONFIRM_SIGNALS`, `confirm_direct`, `cancel_direct`, `walkthrough_plan`, `backward` endpoints, and tag parsing (`<mode:planning>`, `<mode:direct>`) are all gone.

**How to apply:** The system has no explicit mode state. The model decides what to do by calling tools. Write tools pause for confirmation; read tools auto-execute in parallel (ThreadPoolExecutor + NSTask, safe on macOS).
