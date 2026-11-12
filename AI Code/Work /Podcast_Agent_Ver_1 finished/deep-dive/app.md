# app.py — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 248
**Language:** Python 3.10+ (Streamlit)

---

## What This File Does (Plain English)

This is the web UI. It renders a Streamlit page where a user picks a podcast from a dropdown, optionally enables speaker diarisation, chooses a Gemini model, and clicks a button to run the full pipeline. It delegates all actual work to `orchestrator.py` — it owns no pipeline logic itself. Results (summary, transcript, metadata) are displayed in a tabbed view and saved to disk by the orchestrator.

---

## How It Actually Works

### Entry Points

There is no `main()` function. Streamlit re-executes the entire script top-to-bottom on every user interaction. The logical entry points are:

1. **Module load** — page config, API key check, session state init, sidebar render, input widget render.
2. **"Generate summary" button click** — the `if run_clicked:` block (line 131) triggers the pipeline.
3. **History sidebar button click** — reads a saved `.md` file and populates `st.session_state.active`.
4. **"Fetch episode info" button** — a preview-only call to `get_latest_episode()`.

### Data Flow

```
Page load
    → load_podcasts()                   reads podcasts.yaml, populates selectbox
    → OUTPUT_SUMMARIES.glob("*.md")     reads output/summaries/ to populate sidebar history

Button: "Fetch episode info"
    → get_latest_episode(selected["rss"])  preview only; no download
    → estimate_cost(...)                   displays cost estimate

Button: "Generate summary"
    → pipeline_run(...)                    calls orchestrator.run() generator
        ↳ yields string chunks             rendered progressively to summary_placeholder
        ↳ yields result dict (sentinel)    stored in result variable
    → st.session_state.active = {...}     stores result for display
    → st.rerun()                          triggers a full page re-render

Display
    → st.session_state.active             read at bottom of every render cycle
    → tab_summary / tab_transcript / tab_meta  three-tab display
```

### State Management

Streamlit session state holds:

| Key | Type | Purpose |
|---|---|---|
| `st.session_state.active` | dict or None | The currently displayed result. Set after a pipeline run or after clicking a history entry. |

The `active` dict has these keys when from a fresh run: `summary`, `transcript`, `title`, `metadata`, `summary_path`, `transcript_path`, `from_history: False`.

When loaded from history (sidebar click), `active` has: `summary`, `transcript`, `title`, `from_history: True`. The `metadata` key is absent — the Metadata tab shows "Loaded from saved file." in this case.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `on_progress(step, detail)` | **Dead function.** Appends to `progress_log` list. Never called — the actual progress callback is an inline lambda on line 152. |
| (inline lambda line 152) | Calls `step_text.write(f"⏳ {d}")` — the real progress display. |

There are no other standalone functions. All logic is procedural, inline in the script body.

### External Dependencies

| Dependency | What it's used for |
|---|---|
| `orchestrator` | `run`, `load_podcasts`, `get_latest_episode`, `estimate_cost`, error classes, `DEFAULT_MODEL` |
| `streamlit` | Entire UI rendering |
| `python-dotenv` | `load_dotenv()` called at line 24, but env vars are primarily loaded by orchestrator's own `load_dotenv()` at import |
| `pathlib.Path` | Reading history files from `output/summaries/` and `output/transcripts/` |
| `os` | Reading env vars for the API key sanity check |
| `datetime` | Imported but **never used in this file** |

### Error Handling

The `if run_clicked:` block catches four specific exceptions from `orchestrator.py`:

| Exception | UI behaviour |
|---|---|
| `RSSError` | `st.status` → "RSS error", `st.error()`, `st.stop()` |
| `IngestError` | `st.status` → "Download failed", `st.error()`, `st.stop()` |
| `TranscribeError` | `st.status` → "Transcription failed", `st.error()`, `st.stop()` |
| `SummariseError` | `st.status` → "Summarisation failed", `st.error()`, `st.stop()` |

What is NOT caught:
- YAML errors from `load_podcasts()` — crash the entire page
- File read errors when loading history files (sidebar `f.read_text()` on line 65)
- Any exception thrown by `estimate_cost()` or `get_latest_episode()` in the preview expander (only `RSSError` is caught there)
- `st.stop()` halts execution of the current render cycle — it does not kill the server

---

## Non-Technical Decisions Embedded in the Code

- **History sidebar shows at most 10 entries**, most recent first (line 59: `summary_files[:10]`). Older runs are not accessible via the UI.
- **History is loaded by reconstructing the transcript filename** from the summary filename by replacing `_summary` with `_transcript` (line 62). If a summary file exists but its paired transcript file does not, the transcript tab shows empty string — no error.
- **Model dropdown defaults to Pro or Flash based on `DEFAULT_MODEL`** from `.env`. The `index=0 if DEFAULT_MODEL == "gemini-2.5-pro" else 1` logic means any model name other than those two would silently default to Pro.
- **`load_dotenv()` is called twice** — once when `orchestrator.py` is imported (its module-level call) and once explicitly at line 24 of `app.py`. The second call is redundant but harmless.
- **`from datetime import datetime` is imported but never used** (line 6). Leftover from development.
- **The "Upload audio instead of using RSS" expander** does not disable the podcast selectbox. The `podcast_name` from the selectbox is always used as the metadata label, even when processing an upload.
- **API key check uses asymmetric placeholder detection** (lines 37–41): DEEPGRAM is checked for `startswith("your_")`, but GEMINI is not. If a user sets `GOOGLE_API_KEY` to a real value and leaves `GEMINI_API_KEY=your_gemini_key_here`, the check erroneously blocks startup because it inspects `GEMINI_API_KEY` only.

---

## Honest Gaps and Risks

- **Dead code: `on_progress` and `progress_log`** (lines 136–139). The function captures nothing to the UI. The real progress display is the lambda on line 152. Removing `on_progress` would not change any behaviour.
- **`from datetime import datetime` is unused.** Safe to remove.
- **No validation that the upload is actually audio.** The `file_uploader` restricts by extension (`type=["mp3", "wav", ...]`) but Streamlit's check is client-side only. A renamed non-audio file bypasses it and will fail only when Deepgram tries to transcribe it.
- **History loading reads entire `.md` files into memory on every sidebar render.** For large transcripts (long episodes), this happens on every page interaction.
- **`st.rerun()` is called after a successful pipeline run** (line 193). This discards the streaming `summary_placeholder` and re-renders from `session_state.active`. The user briefly sees the streamed content and then it re-renders — functionally fine but visually jarring.
- **No confirmation before running.** The pipeline costs real money. The cost estimate is only visible if the user manually opens the "Preview latest episode from RSS" expander first. Most users will click "Generate summary" without seeing a cost estimate.

---

## Developer Notes

- This file is entirely presentational. All business logic lives in `orchestrator.py`. Adding new pipeline steps should go into `orchestrator.py`; only display changes belong here.
- The `pipeline_run` alias (imported as `run as pipeline_run`) iterates as a generator. The `for item in gen:` loop must keep the `isinstance(item, dict)` check — without it, the result dict gets treated as a text chunk and rendered as Markdown.
- To add a new input type (e.g. RSS episode selector, YouTube URL), the orchestrator's `run()` function signature and the input widget section (lines 82–125) both need changes.
- Streamlit re-runs the whole script on every widget interaction. Code outside `if run_clicked:` runs on every render — keep it fast.
