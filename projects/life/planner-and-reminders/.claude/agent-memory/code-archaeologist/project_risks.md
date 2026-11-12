---
name: Key technical risks and gaps in the codebase
description: Critical risks documented during code archaeology — updated 2026-04-24 to reflect agentic refactor
type: project
---

Risks updated after full documentation pass (2026-04-24). Architecture has been refactored to agentic function-calling; several old risks are resolved, new ones introduced:

**RESOLVED:**
1. ~~`gpt-5.4-nano` invalid model name~~ — fixed; `planner.py` uses `gpt-4o`, `memory.py` uses `gpt-4o-mini`.
2. ~~No rollback on confirm~~ — `confirm_action` in app.py now has a rollback stack for `create_event`, `create_reminder`, and `move_event`.
3. ~~Pipe delimiter corruption~~ — delimiter is TAB (`\t`), not pipe. Tab-in-title is still a corruption risk but much rarer.
4. ~~Reminder `created` date always None~~ — `list_all_open_reminders` now populates `created` from AppleScript `creation date of r`.
5. ~~Conflict detection only checks adjacent pairs~~ — now checks all O(n²) pairs per day.

**STILL ACTIVE:**
1. **`MEMORY_DIR` is a hardcoded absolute path** — `/Users/aryamanchandak/Documents/Obsidian Vault/...`. Will not work on any other machine. No env var fallback.

2. **`confirm_action` rollback does not cover `update_reminder_date` or `delete_event`** — these two write tools push `None` onto the rollback stack. If they succeed and a later action fails, no undo is attempted for them.

3. **No de-duplication** — double-clicking confirm still creates duplicates. The pending state is cleared at the start of confirm_action, so the second click returns early, but the first may have already succeeded.

4. **`get_today_events` returns raw AppleScript date string** for `start` — not `HH:MM`. Inconsistent with `get_week_events`.

5. **`_run_applescript` is copy-pasted** between `apple_calendar.py` and `apple_reminders.py`. Any bug fix must be applied twice.

6. **`session["messages"]` grows unbounded** — no trimming. Long sessions will eventually hit the gpt-4o context limit.

7. **`move_event` does not preserve original duration** — caller must supply `duration_minutes`; defaults to 60.

8. **Overload counting includes all-day events** — birthday reminders can trigger the 4-event overload threshold.

9. **Tab in event/reminder title** — will still corrupt tab-delimited AppleScript output parsing in both apple_calendar.py and apple_reminders.py.

10. **`MEMORY_DIR` reads all .md files** including any non-session Obsidian notes with unrecognisable filenames — silently skipped but could cause confusion.
