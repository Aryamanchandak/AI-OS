# podcast_v1.py — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 641
**Language:** Python 3.10+ (Streamlit)

---

## What This File Does (Plain English)

This is the original single-file proof-of-concept. It contains the full pipeline and the Streamlit UI combined in one script. It accepts a raw URL (including YouTube) or an uploaded file — there is no RSS-feed-to-episode resolution. It does not write files to disk; results exist only in Streamlit session state for the duration of the browser session. It is kept as a reference implementation and is not imported by any other file.

---

## How It Actually Works

### Entry Points

Streamlit executes the entire script top-to-bottom on every interaction. The logical entry points:

1. **Module load** — config, API key check, session state init, sidebar history, input widgets.
2. **"Generate summary" button click** — the `if run_clicked:` block runs the full pipeline inline, displaying progress via `st.write()` and `st.status()`.

### Data Flow

```
User input: URL (direct or YouTube) OR uploaded file
    → ingest(url, upload, upload_name)
        ↳ ingest_youtube(url)       yt_dlp download + FFmpeg extract → tmp/audio/yt_<hash>.mp3
        ↳ ingest_direct_url(url)    streaming HTTP download → tmp/audio/<hash>_<slug>.<ext>
        ↳ ingest_upload(...)        file bytes → tmp/audio/upload_<hash>_<slug>.<ext>
    → estimate_cost(...)            displayed to user
    → transcribe(audio_path)        Deepgram nova-3, cached to tmp/transcripts/<hash>.json
    → stream_summary(...)           Gemini streaming, rendered chunk-by-chunk in UI
    → run_record dict               stored in st.session_state.runs and st.session_state.active
    (no files written to output/)
```

### State Management

| Session state key | Type | Purpose |
|---|---|---|
| `st.session_state.runs` | list of dicts | All completed pipeline runs in this browser session |
| `st.session_state.active` | dict or None | The currently displayed run |

Runs are stored entirely in memory. Closing the browser tab or restarting the Streamlit server discards all history. There is no persistence to disk.

Each run record contains: `timestamp`, `title`, `summary`, `transcript`, `metadata`, `diarised`, `model`.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `estimate_cost(duration, diarise, model)` | Identical to orchestrator version — hardcoded Deepgram and Gemini per-minute rates |
| `build_prompt(...)` | Identical to orchestrator version — formats `SUMMARY_PROMPT` |
| `_is_youtube(url)` | Checks netloc for youtube.com or youtu.be |
| `ingest_youtube(url)` | Uses `yt_dlp` to download video, runs FFmpeg post-processor to extract 128kbps MP3. **Absent from `orchestrator.py`** |
| `ingest_direct_url(url)` | Identical to orchestrator version |
| `ingest_upload(upload, filename)` | Identical to orchestrator version |
| `ingest(url, upload, upload_name)` | Top-level dispatcher: upload wins over URL; dispatches to YouTube or direct based on URL |
| `transcribe(audio_path, diarise)` | Identical to orchestrator version — Deepgram nova-3, JSON cache |
| `stream_summary(...)` | Identical to orchestrator version — Gemini streaming |
| `_filename_slug(s)` | Produces a download filename slug (alphanumeric, max 60 chars) |
| `_friendly_ingest_error(e)` | Maps `IngestError` messages to user-readable strings. **Absent from `app.py`** |

### External Dependencies

Same as `orchestrator.py`, plus:
- `yt_dlp` — YouTube audio download and extraction. **Not imported at module level** — it is imported inside `ingest_youtube()` with an `ImportError` catch. The rest of the app works without it installed.
- `time` — used for wall-clock timing of each pipeline stage (displayed in UI)

### Error Handling

- `IngestError` is caught in the run block; displayed via `_friendly_ingest_error()` which produces friendlier messages than raw exception text.
- `TranscribeError` and `SummariseError` are caught and displayed.
- YouTube failures produce specific friendly messages referencing the upload alternative.
- `yt_dlp` not being installed raises `IngestError("yt-dlp is not installed.")` — handled gracefully.

---

## Key Differences from `orchestrator.py` + `app.py`

| Feature | `podcast_v1.py` | `orchestrator.py` + `app.py` |
|---|---|---|
| YouTube support | Yes — `ingest_youtube()` via `yt_dlp` | No — `_is_youtube()` exists but is dead code |
| RSS feed selection | No — user pastes any URL directly | Yes — curated list from `podcasts.yaml` |
| Output persistence | No — in-memory session state only | Yes — writes `.md` files to `output/` |
| History across sessions | No — resets on server restart | Yes — reads from `output/summaries/` |
| Model selection | No — `DEFAULT_MODEL` from `.env` only | Yes — UI dropdown per run |
| Cost estimate display | Yes — shown during run with timing | Yes — optional preview before run |
| Friendly error messages | Yes — `_friendly_ingest_error()` | No — raw exception message |
| Speaker diarisation | Yes | Yes |
| File size check | Yes — 500 MB | Yes — 500 MB |

---

## Non-Technical Decisions Embedded in the Code

- **`yt_dlp` is a soft dependency** — imported lazily inside `ingest_youtube()`. If not installed, the error is caught and surfaced as an `IngestError` with a helpful message.
- **The sidebar shows the last 5 runs, most recent first** (line 467: `reversed(st.session_state.runs[-5:])`). Older runs from the same session are not accessible.
- **Wall-clock timing** is displayed for each stage (`t0 = time.time()` ... `t1 - t0:.1f}s`). This was removed in the refactored version.
- **Cost estimate is shown during the run**, after ingest but before transcription — so the user sees what they're about to spend on the Deepgram call before it happens.
- **YouTube extraction is set to 128 kbps MP3** regardless of source quality. This is a hardcoded preference in `ydl_opts`.
- **A warning is shown for episodes longer than 4 hours** (line 549: `> 4 * 3600`). No such warning exists in `orchestrator.py`.

---

## Honest Gaps and Risks

- **All results are in-memory.** Closing the tab loses everything — there is no download button for the transcript in the metadata tab (only the summary has a download button). The transcript download button uses `.txt` mime type, not `.md` — the orchestrator version saves `.md`.
- **`SUMMARY_PROMPT` and all pipeline logic is duplicated** from `orchestrator.py` (or rather, `orchestrator.py` was derived from this file). The two are not synced — any fix to one must be manually applied to the other.
- **`_friendly_ingest_error()` is not ported to `app.py`.** Users of the refactored UI see raw exception text instead.
- **The Deepgram transcript cache (`tmp/transcripts/`) is shared** between `podcast_v1.py` and `orchestrator.py`. A transcript cached by one is reused by the other for the same audio file with the same diarise setting.
- **YouTube path resolution after yt_dlp** (lines 192–200) contains a fallback that glob-searches for any file matching the hash pattern. If yt_dlp produces an unexpected filename, the fallback may pick the wrong file.
- **No session state reset button.** Runs accumulate in `st.session_state.runs` until the server restarts. With very long transcripts, memory use grows unbounded.

---

## Developer Notes

- This file is not imported anywhere and can be run independently: `streamlit run podcast_v1.py`.
- If you want to restore YouTube support to the main app, the `ingest_youtube()` function and the `ingest()` dispatcher from this file are the reference implementation to port. You'll also need to add `yt_dlp` to the dependency list and wire `_is_youtube()` back into `orchestrator.py`'s `run()`.
- `_friendly_ingest_error()` is worth porting to `app.py` — the user experience for error messages is noticeably better in v1.
- The shared `tmp/transcripts/` cache means running v1 can accidentally serve a cached transcript to the main app for the same file. This is usually desirable but worth knowing.
