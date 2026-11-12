# memory.py — Technical Documentation

**Last updated:** 2026-04-24
**Lines of code:** 289
**Language:** Python

---

## What This File Does (Plain English)

This module handles reading and writing the persistent session memory stored as markdown files in a hardcoded Obsidian vault directory. On session end, it generates a session title and carry-forward notes via two LLM calls, then assembles and writes a structured markdown file. On session start, it reads recent files, extracts carry-forward notes and the most recent full conversation, and returns a single text block that gets injected into the LLM system prompt. No database — just files on disk at a fixed absolute path.

---

## How It Actually Works

### Entry Points

- **`save_session(messages, modes_visited, current_plan, session_start_time)`** — called from `app.py`'s lifespan shutdown handler and from `POST /new_session`. Orchestrates the full write pipeline.
- **`load_memory_context()`** — called at session start in `app.py`'s lifespan startup and in `POST /new_session`. Returns a string to inject into the system prompt.

### Data Flow

**Writing a session (`save_session`):**
1. Calls `generate_session_title(messages)` — sends the first 6 messages to `gpt-4o-mini`, gets back a 3-5 word hyphenated slug. Falls back to `"general-session"` on any failure.
2. Calls `generate_carry_forward_notes(messages, current_plan)` — sends the full conversation + optional plan JSON to `gpt-4o-mini`, gets back a short bullet list. Returns `"(none)"` if fewer than 3 messages or on any failure.
3. Calls `build_memory_markdown(...)` — assembles the markdown file content from all inputs. No API call.
4. File is named `YYYY-MM-DD_HH-MM_<slug>.md` using `session_start_time`.
5. If a file with that name already exists (same-minute restart), appends `_1`, `_2`, etc. to avoid clobbering.
6. Writes to `MEMORY_DIR` — a hardcoded absolute path to the user's Obsidian vault (see State Management).
7. Returns the absolute path of the written file.

**Loading memory context (`load_memory_context`):**
1. Checks if `MEMORY_DIR` exists. Returns `""` if not.
2. Lists all `.md` files in `MEMORY_DIR`.
3. Parses datetime from each filename with `_parse_filename_date`. Files with unrecognisable names are silently skipped.
4. Sorts files descending by datetime (most recent first).
5. Computes a cutoff at `now - RECENT_DAYS` (7 days).
6. **Pass 1** — for every file within the last 7 days, extracts the `### Carry-Forward Notes` section and accumulates until the `TOKEN_BUDGET_CHARS` (8000) character budget is exhausted.
7. **Pass 2** — if budget remains, extracts the `### Conversation` section from the most recent file only. Truncates to remaining budget with `"... [truncated]"`.
8. Returns all accumulated sections joined as a single string with `## Recent Carry-Forward Notes` and `## Most Recent Session` headers. Returns `""` if nothing found.

### State Management

Module-level constants:
- `MEMORY_DIR = "/Users/aryamanchandak/Documents/Obsidian Vault/Aryamans Vault/Agent MD"` — hardcoded absolute path. Not relative to `__file__`. Writes go to this user's Obsidian vault, not the project directory.
- `TOKEN_BUDGET_CHARS = 8000` — character budget for loaded context (~2000 tokens at 4 chars/token).
- `RECENT_DAYS = 7` — carry-forward notes look-back window.
- `_client` — OpenAI client, initialized once at import.
- `_model = "gpt-4o-mini"` — model for title and notes generation.

No mutable state at module level. Each function operates on its arguments.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `_parse_filename_date(filename)` | Parses `YYYY-MM-DD_HH-MM` from the first two underscore-delimited parts of the filename. Returns `None` on failure. |
| `_extract_section(content, section_header)` | Finds a markdown section by exact string equality of the header line, collects lines until the next `#`-starting line, returns stripped content. |
| `generate_session_title(messages)` | Sends first 6 messages to `gpt-4o-mini`, sanitises output to alphanumeric+hyphen slug via character replacement. Falls back to `"general-session"` on any exception. |
| `generate_carry_forward_notes(messages, current_plan)` | Sends full conversation + optional plan JSON to `gpt-4o-mini`, returns a markdown bullet list. Returns `"(none)"` on failure or if session has 2 or fewer messages. |
| `build_memory_markdown(session_dt, title, modes_visited, messages, current_plan, carry_forward)` | Pure string assembly — no API call. Builds the complete markdown file content including conversation, plan JSON, and carry-forward notes. |
| `save_session(messages, modes_visited, current_plan, session_start_time)` | Orchestrates title + notes generation, markdown build, collision-safe disk write. Returns the file path written. |
| `load_memory_context()` | Reads and filters memory files from `MEMORY_DIR`, returns a formatted context string for system prompt injection. |

### External Dependencies

- **OpenAI API** — `chat.completions.create` used in `generate_session_title` and `generate_carry_forward_notes`. Both calls use `timeout=30`.
- **`_model = "gpt-4o-mini"`** — valid model name. Both LLM calls will succeed with a correctly configured `OPENAI_API_KEY`.
- **`MEMORY_DIR`** — hardcoded to `/Users/aryamanchandak/Documents/Obsidian Vault/Aryamans Vault/Agent MD`. The directory is created with `os.makedirs(..., exist_ok=True)` inside `save_session`, not at import time.
- **`sys.stderr`** — used for warning messages when a file cannot be read during `load_memory_context`.
- **Standard library:** `os`, `sys`, `json`, `datetime`.

### Error Handling

| Failure | Handling |
|---|---|
| `generate_session_title` — any exception | Caught, returns `"general-session"` |
| `generate_carry_forward_notes` — any exception | Caught, returns `"(none)"` |
| `load_memory_context` — single file unreadable | Caught per-file, warning printed to stderr, file skipped |
| `load_memory_context` — `MEMORY_DIR` does not exist | Checked upfront with `os.path.exists`, returns `""` |
| `save_session` — disk write fails | Exception propagates to caller (`app.py` catches with a bare `except Exception: pass`) |

---

## Non-Technical Decisions Embedded in the Code

- **`MEMORY_DIR` is a hardcoded absolute path to an Obsidian vault** — this means memory files go into the user's Obsidian knowledge base, not the project directory. The path will not work on any other machine without editing `memory.py` directly.
- **`_model = "gpt-4o-mini"`** — deliberately the smaller, cheaper model. The comment notes "mini is sufficient for title/notes generation, faster and cheaper." This is the only module using `gpt-4o-mini`; `planner.py` uses `gpt-4o`.
- **Character budget as proxy for token count** — `TOKEN_BUDGET_CHARS = 8000` at ~4 chars/token estimates 2000 tokens. Unicode text, code, or JSON will consume more tokens per character than this estimate.
- **Carry-forward notes are accumulated from ALL files in the last 7 days** — but only the most recent file contributes its full conversation. A session from 6 days ago can contribute carry-forward notes but not its full conversation.
- **`generate_session_title` only looks at the first 6 messages** — long sessions where the topic shifts will get a title based on the opening conversation only.
- **`_extract_section` matches section headers by exact string equality** — `line.strip() == section_header.strip()`. Files with `###Carry-Forward Notes` (no space after `###`) will not match `"### Carry-Forward Notes"`. Files produced by `build_memory_markdown` always use the correct format.
- **`build_memory_markdown` labels all non-user messages as `"Bot"`** — any `role != "user"` message gets the speaker label `"Bot"` in the file. The internal `"ai"` role value used in `session["messages"]` is normalized here.
- **Slug sanitization in `generate_session_title`** — replaces any non-alphanumeric, non-hyphen character with `-`, collapses multiple hyphens, strips leading/trailing hyphens. Spaces become hyphens; special characters disappear.
- **File collision avoidance** — if a file with the computed name already exists (same-minute session restart), appends `_1`, `_2` counter. Prevents overwriting the original session file.
- **`save_session` is called with `modes_visited=["chat"]` from both call sites in `app.py`** — the old mode tracking is gone. The session file always shows "Modes visited: chat" regardless of what tools were called.

---

## Honest Gaps and Risks

- **`MEMORY_DIR` is hardcoded** — the app will silently fail to load or save memory on any machine that is not the developer's own, or if the Obsidian vault is moved. There is no env var fallback.
- **`load_memory_context` reads all `.md` files in `MEMORY_DIR`** — if the Obsidian vault contains many markdown files that do not follow the `YYYY-MM-DD_HH-MM_title.md` naming convention, `_parse_filename_date` will return `None` for them and they will be silently skipped. This is safe but means any manually created or imported notes in that folder are invisible to the system.
- **Budget accounting uses `len(chunk)` (characters)** — multi-byte Unicode or dense JSON will consume more tokens than the 2000-token estimate.
- **`generate_carry_forward_notes` passes the full conversation to the LLM** — for a very long session, this could be tens of thousands of characters. With `timeout=30`, this call may time out on long sessions. The timeout exception is caught and falls back to `"(none)"`.
- **`save_session` is called both on clean shutdown and on `/new_session`** — if the user clicks "New Session" and then the server also shuts down cleanly, a second save attempt is made. The filename collision counter prevents overwrite but produces a `_1` variant file.
- **`_extract_section` stops at any line starting with `#`** — if a user typed a markdown heading (e.g. `# My notes`) inside a chat message, that line will prematurely terminate section extraction during `load_memory_context`.
- **`load_memory_context` loads the most recent file's full conversation regardless of age** — if the user hasn't used the app in three weeks, the most recent file (from three weeks ago) is still loaded in full. There is no maximum age for the conversation load, only for carry-forward notes (7 days).

---

## Developer Notes

- `save_session` is the only write path. It is called in two places in `app.py`, both wrapped in `except Exception: pass`. Failures are completely silent. If memory files are not appearing on disk, add temporary logging to those call sites.
- `load_memory_context` returns a raw string that is injected as a second system message in `build_system_messages()` in `planner.py`. The format uses `## Recent Carry-Forward Notes` and `## Most Recent Session` headers.
- If you want to change `MEMORY_DIR`, consider converting it to an environment variable: `MEMORY_DIR = os.getenv("MEMORY_DIR", "/Users/aryamanchandak/Documents/Obsidian Vault/Aryamans Vault/Agent MD")`. This would make the app portable without code changes.
- The `MEMORY_DIR` is an absolute path, not derived from `__file__`. Moving `memory.py` to a different directory has no effect on where files are written.
