# .env — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 3
**Language:** Shell environment file (dotenv format)

---

## What This File Does (Plain English)

Holds the three secrets and one configuration value the application needs at runtime. It is read at startup by both `orchestrator.py` and `app.py` via `python-dotenv`'s `load_dotenv()`. Without valid values here, both the CLI and the UI halt immediately.

---

## Variables

| Variable | Purpose | Default in repo |
|---|---|---|
| `DEEPGRAM_API_KEY` | Authenticates all calls to Deepgram's speech-to-text REST API | `your_deepgram_key_here` (placeholder) |
| `GEMINI_API_KEY` | Authenticates calls to Google's Gemini generative API | `your_gemini_key_here` (placeholder) |
| `GEMINI_MODEL` | Selects which Gemini model to use for summarisation | `gemini-2.5-pro` |

---

## Non-Technical Decisions Embedded in the Config

- The file ships with placeholder strings (`your_deepgram_key_here`, `your_gemini_key_here`) — the application must check for these at startup or it will call APIs with literal placeholder strings and get auth errors, not a clear message.
- `GEMINI_MODEL` is optional — if omitted, `orchestrator.py` falls back to `"gemini-2.5-pro"` at module level. The `.env` exists partly to switch to `gemini-2.5-flash` cheaply without changing code.
- There is also an alternative `GOOGLE_API_KEY` accepted by the summariser code (both `orchestrator.py` and `podcast_v1.py`). This is not documented in `.env` — a user who sets `GOOGLE_API_KEY` instead of `GEMINI_API_KEY` must know this from reading the source, not the config file.

---

## Honest Gaps and Risks

- No `.env.example` file exists in the repo. There is a reference to one in `podcast_v1.py`'s error message (`"Set them in your .env (see .env.example)"`) but the file does not exist — a new developer has no template to copy.
- The startup check in `app.py` inspects `GEMINI_API_KEY` for a `"your_"` prefix but does NOT check `GOOGLE_API_KEY` for the same prefix. If a user leaves `GEMINI_API_KEY=your_gemini_key_here` and sets a real value in `GOOGLE_API_KEY`, the placeholder check fires incorrectly and blocks startup.
- This file is almost certainly committed to the repo without real keys (the placeholder values indicate it). That is correct. But it is one edit away from leaking credentials if a developer replaces the placeholders without adding `.env` to `.gitignore`.

---

## Developer Notes

- Add `.env` to `.gitignore` before populating real keys.
- Create a `.env.example` file with the three variable names and placeholder comments — the reference in `podcast_v1.py` expects it to exist.
- The model name in `GEMINI_MODEL` is passed directly to the Gemini API — typos produce an API error at summarisation time, not at startup.
