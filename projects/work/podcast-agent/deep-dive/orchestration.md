# System Orchestration — How It All Fits Together

**Last updated:** 2026-05-10

---

## System Overview

This is a podcast summarisation pipeline with two modes of use: a Streamlit web UI (`app.py`) and a command-line interface (`orchestrator.py --main`). Given a podcast's RSS feed (or an uploaded audio file), it downloads the latest episode, transcribes it with Deepgram, summarises the transcript with Gemini, and saves both outputs as Markdown files. A reference single-file version (`podcast_v1.py`) also exists but runs independently and does not persist to disk.

---

## Component Map

| File | Role |
|---|---|
| `.env` | Secrets and model selection — loaded at startup by both entry points |
| `podcasts.yaml` | Curated list of podcast RSS feeds — the only way to add podcasts |
| `orchestrator.py` | The entire pipeline: RSS parsing, audio download, Deepgram transcription, Gemini summarisation, Markdown file writing. Also runnable as a CLI. |
| `app.py` | Streamlit UI layer. Owns no pipeline logic. Reads from `orchestrator.py` and `output/` only. |
| `podcast_v1.py` | Original proof-of-concept — self-contained, no file persistence. Reference only. Not imported. |
| `output/transcripts/` | Written by `orchestrator.py`. Read by `app.py` sidebar history. |
| `output/summaries/` | Written by `orchestrator.py`. Read by `app.py` sidebar history. |
| `tmp/audio/` | Intermediate audio files. Written and read by `orchestrator.py`. Never deleted. |
| `tmp/transcripts/` | Deepgram response cache (JSON). Written and read by `orchestrator.py` (and `podcast_v1.py`). Never deleted. |

---

## Data & Control Flow

### Via the Streamlit UI (`app.py`)

```
1. Streamlit renders page
2. app.py calls load_podcasts() → reads podcasts.yaml → populates dropdown
3. app.py glob-reads output/summaries/*.md → populates sidebar history

4. User picks podcast, sets options, clicks "Generate summary"

5. app.py calls pipeline_run() = orchestrator.run() as a generator

6. orchestrator.run() calls get_latest_episode(rss_url)
   → feedparser parses RSS feed over HTTP
   → returns {url, title, published, duration_seconds}

7. orchestrator.run() calls ingest_direct_url(episode_url)
   → streams audio via requests to tmp/audio/<hash>_<slug>.<ext>
   → mutagen reads duration from file metadata

8. orchestrator.run() calls transcribe(audio_path, diarise)
   → computes SHA-256 of audio file
   → checks tmp/transcripts/<hash>[_diar].json
   → cache hit: returns immediately
   → cache miss: reads entire file into memory, POSTs to Deepgram nova-3
   → formats response into paragraph text (with or without speaker labels)
   → writes JSON cache

9. orchestrator.run() calls save_transcript()
   → writes output/transcripts/<YYYYMMDD>_<Podcast>_<Episode>_transcript.md

10. orchestrator.run() calls stream_summary()
    → builds SUMMARY_PROMPT with transcript + metadata
    → calls Gemini generate_content_stream()
    → yields text chunks one by one

11. app.py receives each yielded chunk:
    → isinstance(item, dict) is False → appends to buffer → renders to summary_placeholder

12. orchestrator.run() assembles full summary → calls save_summary()
    → writes output/summaries/<YYYYMMDD>_<Podcast>_<Episode>_summary.md
    → yields result dict (the sentinel)

13. app.py receives result dict:
    → isinstance(item, dict) is True → stores in result variable
    → sets st.session_state.active = {...}
    → calls st.rerun()

14. Streamlit re-renders page → displays tabbed view from session_state.active
```

### Via the CLI (`orchestrator.py` direct)

```
1. load_podcasts() reads podcasts.yaml
2. User picks a number
3. run() generator is iterated
4. String chunks printed to stdout as they arrive (flush=True)
5. Result dict printed as "Done." with file paths
```

### Via the history sidebar

```
1. User clicks a history button in sidebar
2. app.py reads output/summaries/<file>.md → session_state.active["summary"]
3. app.py derives transcript path: replaces "_summary" with "_transcript"
4. app.py reads output/transcripts/<file>.md → session_state.active["transcript"]
   (silently empty string if file does not exist)
5. st.rerun() → tabbed display from session_state.active
```

---

## Mode / State Machine

There is no explicit mode or state machine. The application has a single active-result concept managed through `st.session_state.active`:

| Transition | Trigger | Result |
|---|---|---|
| `None` → result | User completes a pipeline run | `active` set with full metadata |
| `None` → result | User clicks history sidebar button | `active` set with `from_history: True`, no metadata |
| result → result | User runs the pipeline again or clicks history | Previous `active` overwritten |
| result → `None` | Not possible via the UI — session_state persists for the session |

The `from_history` flag controls which fields are available in the Metadata tab — metadata is not stored inside the `.md` files, so history-loaded results cannot display it.

---

## Key Integration Points

### The `run()` generator protocol

`orchestrator.run()` is a generator that mixes two item types in the same iterator:
- **String chunks** — fragments of the Gemini streaming response
- **A result dict** — the final sentinel, yielded exactly once after saving files

Both `app.py` (line 157–162) and the CLI (line 585–591) use `isinstance(item, dict)` to detect the sentinel. Any new caller of `run()` must implement this pattern — breaking this convention silently produces a dict rendered as Markdown text in the UI or printed as noise in the CLI.

### Output filename coupling

`app.py`'s history sidebar assumes the output filename format produced by `_output_slug()`:
- Summary: `<YYYYMMDD>_<Podcast>_<Episode>_summary.md`
- Transcript: `<YYYYMMDD>_<Podcast>_<Episode>_transcript.md`

The sidebar reconstructs the transcript path by string-replacing `"_summary"` with `"_transcript"` on the summary filename. If `_output_slug()` changes its format, this derivation will silently fail — returning empty transcript text without an error.

### Shared transcript cache

Both `orchestrator.py` and `podcast_v1.py` cache Deepgram results in `tmp/transcripts/` using the same key scheme (SHA-256 of file content + diarise flag). A transcript cached by one is transparently reused by the other for the same audio file.

### API key sources

The summariser accepts `GEMINI_API_KEY` or `GOOGLE_API_KEY` (whichever is non-empty, in that order). The UI's startup check only validates `GEMINI_API_KEY`. If a user sets only `GOOGLE_API_KEY`, the UI blocks at startup even though the pipeline would succeed.

---

## External Dependencies (System-Level)

| Dependency | Where used | Required? |
|---|---|---|
| `DEEPGRAM_API_KEY` in `.env` | `orchestrator.py`, `podcast_v1.py` | Yes |
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` in `.env` | `orchestrator.py`, `podcast_v1.py` | Yes |
| `GEMINI_MODEL` in `.env` | `orchestrator.py`, `podcast_v1.py` | No (defaults to `gemini-2.5-pro`) |
| Deepgram API (nova-3 model) | `orchestrator.py`, `podcast_v1.py` | Yes — hardcoded, no override |
| Gemini API (`gemini-2.5-pro` or `gemini-2.5-flash`) | `orchestrator.py`, `podcast_v1.py` | Yes |
| RSS feed reachability | `orchestrator.py` | Yes for RSS mode |
| Audio host reachability | `orchestrator.py`, `podcast_v1.py` | Yes for URL mode |
| `yt_dlp` + FFmpeg | `podcast_v1.py` only | No (soft dependency) |
| Local disk write access to `tmp/` and `output/` | `orchestrator.py` | Yes |
| Streamlit server | `app.py` | Yes for web UI |

---

## Known Architectural Risks

1. **YouTube support is silently missing in the production path.** `_is_youtube()` exists in `orchestrator.py` but is never called. A user who pastes a YouTube URL into the upload box will get a download failure, not a helpful error. `podcast_v1.py` handles YouTube correctly — the feature was dropped in the refactor without a replacement.

2. **Same-day filename collisions.** `_output_slug()` uses `%Y%m%d`. Running the same podcast twice on the same day produces identical slugs, and `save_transcript()` / `save_summary()` use `Path.write_text()` which overwrites without warning. The first run's files are silently destroyed.

3. **Relative paths to cwd.** All `tmp/` and `output/` paths are relative. Launching `orchestrator.py` from a different working directory (e.g. `python Code/Agents/Podcast-Agent/orchestrator.py`) creates orphaned `tmp/` and `output/` trees elsewhere on disk.

4. **The transcript cache never invalidates on options changes.** The cache key is `SHA-256(file_contents) + diarise_flag`. Changing the Deepgram model or any other `PrerecordedOptions` parameter does not invalidate cached results. Users who toggle diarisation correctly get separate caches; users who change `smart_format`, `punctuate`, or model get stale results silently.

5. **Entire audio file loaded into RAM for transcription.** `transcribe()` reads the whole file with `f.read()` before sending to Deepgram. At the 500 MB limit, this is 500 MB of Python heap. On a machine with constrained memory, this will cause an OOM or slow transcription significantly.

6. **No cleanup of `tmp/audio/`.** Every run downloads a new audio file. Downloaded files accumulate indefinitely — there is no TTL, no size limit check on the tmp directory, and no UI to trigger cleanup.

7. **Logic and display duplication between v1 and the refactored version.** `SUMMARY_PROMPT`, `estimate_cost()`, `build_prompt()`, `transcribe()`, `ingest_direct_url()`, and `ingest_upload()` are near-identical between `podcast_v1.py` and `orchestrator.py`. Bug fixes in one must be manually applied to the other.
