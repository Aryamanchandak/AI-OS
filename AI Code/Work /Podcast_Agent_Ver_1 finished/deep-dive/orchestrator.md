# orchestrator.py — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 592
**Language:** Python 3.10+

---

## What This File Does (Plain English)

This is the entire backend pipeline. It takes a podcast name and RSS URL (or an uploaded audio file), downloads the audio, transcribes it with Deepgram, summarises the transcript with Gemini, and saves both the transcript and summary as Markdown files. It is designed to be imported by `app.py` or run directly from the command line.

---

## How It Actually Works

### Entry Points

There are two entry points:

1. **`run()`** — the main pipeline function. Called by `app.py`. It is a **generator function** (it uses `yield`), which means calling it returns a generator object; nothing executes until the caller iterates over it.
2. **`if __name__ == "__main__"` block** (line 564–591) — a minimal CLI that reads `podcasts.yaml`, prompts the user to pick a podcast, then iterates `run()` and prints progress.

### Data Flow

```
podcasts.yaml
    → load_podcasts()           returns list of {name, rss}
    → get_latest_episode(rss)   HTTP GET to RSS URL, returns {url, title, published, duration_seconds}
    → ingest_direct_url(url)    streams audio to tmp/audio/<hash>_<slug>.<ext>
                                 OR
    → ingest_upload(upload)     writes uploaded bytes to tmp/audio/upload_<hash>_<slug>.<ext>
    → transcribe(audio_path)    reads file, sends to Deepgram nova-3, caches JSON in tmp/transcripts/
    → stream_summary(...)       builds prompt, calls Gemini generate_content_stream(), yields text chunks
    → save_transcript(...)      writes output/transcripts/<slug>_transcript.md
    → save_summary(...)         writes output/summaries/<slug>_summary.md
    → yields result dict        final sentinel item from the generator
```

### State Management

No persistent in-memory state. The file creates four directories at import time (lines 36–38):
- `tmp/audio/` — downloaded/uploaded audio files (not cleaned up automatically)
- `tmp/transcripts/` — Deepgram JSON response cache
- `output/transcripts/` — final Markdown transcripts
- `output/summaries/` — final Markdown summaries

All paths are relative to the current working directory at runtime.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `load_podcasts()` | Reads `podcasts.yaml` with `yaml.safe_load`, returns the `podcasts` list or `[]` if file missing |
| `get_latest_episode(rss_url)` | Parses the RSS feed with `feedparser`, returns metadata for `feed.entries[0]` only |
| `estimate_cost(duration, diarise, model)` | Returns a hardcoded cost estimate dict using fixed per-minute rates for Deepgram and per-90-min rates for Gemini |
| `ingest_direct_url(url)` | Streams audio from URL to `tmp/audio/`, enforces 500 MB limit during download |
| `ingest_upload(upload, filename)` | Reads an upload object entirely into memory, then writes to `tmp/audio/` |
| `transcribe(audio_path, diarise)` | Checks JSON cache first; on miss, reads entire file into memory and POSTs to Deepgram |
| `_format_diarised(response)` | Extracts paragraph-level speaker-labelled text from Deepgram response dict |
| `_format_plain(response)` | Extracts paragraph text without speaker labels; falls back to raw `transcript` string on parse failure |
| `stream_summary(...)` | Builds the summary prompt and calls `client.models.generate_content_stream()`; yields raw text chunks |
| `build_prompt(...)` | String-formats `SUMMARY_PROMPT` with episode metadata and transcript |
| `_output_slug(podcast_name, episode_title)` | Produces a `YYYYMMDD_PodcastName_EpisodeTitle` filename slug |
| `save_transcript(slug, ...)` | Writes Markdown file to `output/transcripts/` |
| `save_summary(slug, ...)` | Writes Markdown file to `output/summaries/` |
| `run(...)` | **Generator.** Orchestrates all of the above. Yields string chunks during summarisation, then yields the final result dict as the last item |
| `_is_youtube(url)` | Checks if a URL is YouTube — **defined but never called in this file** |
| `_slug(s, max_len)` | Replaces non-alphanumeric characters with underscores, truncates to max_len |
| `_hash_url(url)` | SHA-256 of the URL, first 16 hex chars — used for deduplicating audio file names |
| `_file_hash(path)` | SHA-256 of file contents, first 24 hex chars — used as transcript cache key |
| `_cache_path(audio_path, diarise)` | Computes the JSON cache file path from file hash + diarise flag |
| `_audio_duration(path)` | Reads audio duration from file metadata via mutagen; returns 0.0 on any error |
| `_human_duration(seconds)` | Converts seconds to "Xh Ym" or "Ym" string |

### The `run()` Generator — Critical Detail

`run()` is declared with `yield` inside it, making it a generator. It serves **two different types of items** through the same iterator:

1. **String chunks** — each piece of Gemini's streaming response, as it arrives. Callers append these to a buffer and can render them progressively.
2. **A result dict** — yielded exactly once at the end (line 557) as a sentinel to signal completion. The dict contains `transcript_path`, `summary_path`, `summary_text`, `transcript_text`, and `metadata`.

Callers must distinguish between these: `if isinstance(item, dict)` for the sentinel, otherwise treat as a string chunk. Both the CLI (line 586) and `app.py` (line 158) do this. This is a tight coupling — any new caller must know this convention.

### External Dependencies

| Dependency | What it's used for |
|---|---|
| `feedparser` | Parsing RSS XML feeds |
| `requests` | Streaming audio download |
| `deepgram` (DeepgramClient, PrerecordedOptions) | Speech-to-text transcription API |
| `google.genai` | Gemini generative model for summarisation |
| `mutagen` | Reading audio file duration from metadata |
| `yaml` | Parsing `podcasts.yaml` |
| `python-dotenv` (load_dotenv) | Loading `.env` at module import |
| `pathlib.Path` | All file I/O |
| `hashlib` | Generating cache keys |
| `re` | Slug generation |

### Error Handling

Four custom exception classes are defined and raised at specific failure points:

| Exception | When raised |
|---|---|
| `RSSError` | Feed cannot be parsed, feed has no entries, or latest episode has no audio enclosure |
| `IngestError` | Audio URL download fails (network error, 4xx/5xx), declared size > 500 MB, file exceeds 500 MB during streaming, unsupported format for uploads |
| `TranscribeError` | `DEEPGRAM_API_KEY` not set, or any exception from the Deepgram SDK |
| `SummariseError` | `GEMINI_API_KEY` not set, or any exception from the Gemini SDK |

What is NOT caught:
- `yaml.safe_load()` errors (malformed YAML crashes at `load_podcasts()`)
- File I/O errors when writing to `output/` or `tmp/` (e.g. disk full, permissions)
- `mutagen` errors are caught and return 0.0, but silently — callers see duration as 0
- Any exception that occurs inside the generator after `yield chunk` (streaming) is not caught by the `run()` function itself

---

## Non-Technical Decisions Embedded in the Code

- **Only the latest episode is ever fetched.** `get_latest_episode()` always takes `feed.entries[0]`. There is no mechanism to pick by date, title, or episode number.
- **Transcript cache is keyed on file content hash + diarise flag only.** Changing Deepgram model or any other option (e.g. `smart_format`, `punctuate`) does not invalidate the cache. A stale cached transcript will be used even if you change transcription settings.
- **The entire audio file is loaded into memory before sending to Deepgram** (line 383: `payload = {"buffer": f.read()}`). For a 500 MB file, this means 500 MB of RAM is consumed at transcription time.
- **Cost estimates are hardcoded rates** (line 143–146). Deepgram at $0.0043/min, Gemini Pro at $0.40/90 min, Gemini Flash at $0.05/90 min. These will silently go stale if pricing changes.
- **`ingest_upload()` also loads the entire file into memory twice** — once via `upload.read()` and once when `_audio_duration()` opens the saved file. For large uploads this is wasteful.
- **YouTube support was removed.** The `_is_youtube()` function exists at line 228 but is never called. It was present in `podcast_v1.py` and appears to have been left as dead code during the refactor.
- **`import time` at line 10 is unused.** Carried over from `podcast_v1.py`.
- **Output filenames are date-stamped but not time-stamped.** `_output_slug()` uses `%Y%m%d`. Two runs of the same podcast on the same day produce the same filename slug and silently overwrite each other.

---

## Honest Gaps and Risks

- **Same-day filename collision.** Two runs of the same podcast on the same day will produce the same `_output_slug()` and overwrite `output/transcripts/` and `output/summaries/` files without warning.
- **No cleanup of `tmp/audio/`.** Downloaded audio files accumulate indefinitely. A high-volume deployment would fill disk.
- **All paths are relative to cwd.** Running from a different directory (e.g. `python path/to/orchestrator.py` from another folder) silently creates `tmp/` and `output/` in the wrong place.
- **`_is_youtube()` is dead code.** It was never wired up in this version of the file. If YouTube support is intended, the `ingest()` dispatcher from `podcast_v1.py` needs to be ported over, along with the `yt_dlp` dependency.
- **The Deepgram model is hardcoded as `"nova-3"`** (line 388). There is no way to override it via the UI or config without editing the source.
- **No retry logic anywhere.** A transient network failure during audio download, Deepgram transcription, or Gemini summarisation raises an exception immediately with no retry.
- **`feedparser.bozo`** (line 84) is only checked alongside an empty entries list. A feed with a parse warning (`bozo=True`) but valid entries will be processed silently — the RSS warning is swallowed.
- **Duration from RSS vs from file may diverge.** The RSS `itunes_duration` field is used if present and non-zero, overriding the mutagen-read duration. `itunes_duration` is author-declared and can be wrong.

---

## Developer Notes

- When editing the summarisation prompt (`SUMMARY_PROMPT`), the transcript cache will still return old Deepgram results — only the Gemini call re-runs.
- The `run()` function is a generator. Do not call it and then check a return value — you must iterate it. The result dict is the last item yielded, not a return value.
- Any new feature that needs progress reporting should call `progress_callback(step, detail)` at the start of each stage — the callback is optional and no-ops if not provided.
- `ingest_upload()` expects either a file-like object (with `.read()`) or bytes-like. Streamlit's `UploadedFile` has `.read()` and works. Passing a plain `bytes` object also works via `bytes(upload)`.
- The `GOOGLE_API_KEY` environment variable is accepted as an alias for `GEMINI_API_KEY` in `stream_summary()` (line 421). This is not documented externally.
