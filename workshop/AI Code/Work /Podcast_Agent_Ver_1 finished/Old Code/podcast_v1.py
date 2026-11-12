"""Podcast Summariser POC — single-file Streamlit app.

Run with:  streamlit run app.py
"""
import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

import requests
import streamlit as st
from dotenv import load_dotenv
from google import genai
from mutagen import File as MutagenFile

load_dotenv()

# =============================================================================
# Config
# =============================================================================

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
TMP_AUDIO = Path("tmp/audio")
TMP_TRANSCRIPTS = Path("tmp/transcripts")
TMP_AUDIO.mkdir(parents=True, exist_ok=True)
TMP_TRANSCRIPTS.mkdir(parents=True, exist_ok=True)

MAX_BYTES = 500 * 1024 * 1024  # 500 MB
SUPPORTED_EXTS = {"mp3", "wav", "m4a", "mp4", "ogg", "flac", "aac"}


class IngestError(Exception):
    pass


class TranscribeError(Exception):
    pass


class SummariseError(Exception):
    pass


# =============================================================================
# Cost estimation
# =============================================================================

TRANSCRIBE_MODEL = "gemini-2.0-flash"


def estimate_cost(duration_seconds: float, diarise: bool, model: str) -> dict:
    """USD cost + rough wall-clock minutes for a single run."""
    minutes = max(duration_seconds / 60, 0.0)
    # Gemini 2.0 Flash audio input: ~25 tokens/sec at $0.075/1M tokens
    transcription = 0.075 * 25 * 60 * minutes / 1_000_000
    gemini_per_90 = 0.05 if model == "gemini-2.5-flash" else 0.40
    gemini = transcription + gemini_per_90 * (minutes / 90)
    summary_seconds = 20 if model == "gemini-2.5-flash" else 40
    time_minutes = 0.5 + (minutes / 30) + summary_seconds / 60
    return {
        "gemini_usd": gemini,
        "total_usd": gemini,
        "estimated_minutes": time_minutes,
    }


# =============================================================================
# Prompt
# =============================================================================

SUMMARY_PROMPT = """You are a senior research analyst summarising a podcast episode for a busy
executive who will not listen to it. Your output is the only record of this
conversation they will see.

Episode metadata:
- Title: {title}
- Source: {source_url}
- Duration: {duration_human}
{speaker_count_line}

Transcript:
{transcript}

Produce a Markdown summary with these sections, in order:

## TL;DR
Three sentences. What was the conversation about, what was the central tension
or thesis, and what is the single most important thing the executive should know.

## Main topics
Five to eight bullets. Each bullet is one sentence framing what was discussed.
Order by where in the episode they appeared. Do not editorialise.

## Notable claims & moments
Five to ten bullets. Each bullet starts with a [HH:MM:SS] timestamp inferred
from where in the transcript the claim appears (estimate based on transcript
position). Quote or paraphrase tightly. Include claims that are surprising,
contested, predictive, or specific enough to fact-check.

## People & works mentioned
Bullets. Names of people, organisations, books, papers, or products mentioned,
with one-line context for each. Skip the host and guest themselves; this is for
others mentioned in passing.

## What this episode is good for
Two sentences. Who would benefit from listening to the full thing, and who can
safely skip it.

Constraints:
- Be specific. Avoid generalities like "they discussed AI." Always name the
  specific topic, technology, person, or claim.
- Stay under 1500 words total.
- If something cannot be inferred from the transcript, omit it. Never invent.
- Use the same names and terms the speakers use; do not normalise.
"""


def _human_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m" if h else f"{m}m"


def build_prompt(transcript, title, source_url, duration_seconds, speaker_count):
    return SUMMARY_PROMPT.format(
        title=title or "Untitled episode",
        source_url=source_url or "Uploaded file",
        duration_human=_human_duration(duration_seconds),
        speaker_count_line=(
            f"- Speakers identified: {speaker_count}" if speaker_count else ""
        ),
        transcript=transcript,
    )


# =============================================================================
# Ingest — URL/upload to local audio path + metadata
# =============================================================================

def _is_youtube(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "youtube.com" in host or "youtu.be" in host


def _slug(s: str, max_len: int = 80) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "").strip("_")[:max_len] or "file"


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _audio_duration(path: Path) -> float:
    try:
        f = MutagenFile(str(path))
        if f and f.info and getattr(f.info, "length", None):
            return float(f.info.length)
    except Exception:
        pass
    return 0.0


def ingest_youtube(url: str) -> dict:
    try:
        import yt_dlp
    except ImportError as e:
        raise IngestError("yt-dlp is not installed.") from e

    out_template = str(TMP_AUDIO / f"yt_{_hash_url(url)}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base = Path(ydl.prepare_filename(info))
    except Exception as e:
        raise IngestError(f"YouTube download failed: {e}") from e

    audio_path = base.with_suffix(".mp3")
    if not audio_path.exists():
        candidates = [
            p for p in TMP_AUDIO.glob(f"yt_{_hash_url(url)}.*")
            if p.suffix.lower().lstrip(".") in SUPPORTED_EXTS
        ]
        if not candidates:
            raise IngestError("yt-dlp didn't produce a usable audio file.")
        audio_path = candidates[0]

    return {
        "path": str(audio_path),
        "title": info.get("title") or "YouTube episode",
        "duration_seconds": float(info.get("duration") or _audio_duration(audio_path)),
        "source_url": url,
        "source_type": "youtube",
    }


def ingest_direct_url(url: str) -> dict:
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()

            declared_size = int(r.headers.get("content-length", 0))
            if declared_size and declared_size > MAX_BYTES:
                raise IngestError(
                    f"Audio file too large ({declared_size / 1e6:.0f} MB > 500 MB)."
                )

            ctype = r.headers.get("content-type", "").lower()
            url_lower = url.lower()
            if "mpeg" in ctype or url_lower.endswith(".mp3"):
                ext = "mp3"
            elif "wav" in ctype or url_lower.endswith(".wav"):
                ext = "wav"
            elif "mp4" in ctype or "m4a" in ctype or url_lower.endswith((".m4a", ".mp4")):
                ext = "m4a"
            elif "ogg" in ctype or url_lower.endswith(".ogg"):
                ext = "ogg"
            else:
                ext = "mp3"

            stem = _slug(Path(urlparse(url).path).stem) or "episode"
            audio_path = TMP_AUDIO / f"{_hash_url(url)}_{stem}.{ext}"

            written = 0
            with open(audio_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    written += len(chunk)
                    if written > MAX_BYTES:
                        f.close()
                        audio_path.unlink(missing_ok=True)
                        raise IngestError("Audio file exceeded 500 MB during download.")
                    f.write(chunk)
    except requests.RequestException as e:
        raise IngestError(f"Could not download audio: {e}") from e

    return {
        "path": str(audio_path),
        "title": Path(urlparse(url).path).stem or "Untitled",
        "duration_seconds": _audio_duration(audio_path),
        "source_url": url,
        "source_type": "direct_url",
    }


def ingest_upload(upload, filename: str) -> dict:
    suffix = Path(filename).suffix.lower().lstrip(".") or "mp3"
    if suffix not in SUPPORTED_EXTS:
        raise IngestError(f"Unsupported audio format: .{suffix}")

    data = upload.read() if hasattr(upload, "read") else bytes(upload)
    if len(data) > MAX_BYTES:
        raise IngestError(f"File too large ({len(data) / 1e6:.0f} MB > 500 MB).")

    h = hashlib.sha256(data).hexdigest()[:16]
    audio_path = TMP_AUDIO / f"upload_{h}_{_slug(Path(filename).stem)}.{suffix}"
    audio_path.write_bytes(data)

    return {
        "path": str(audio_path),
        "title": Path(filename).stem,
        "duration_seconds": _audio_duration(audio_path),
        "source_url": "Uploaded file",
        "source_type": "upload",
    }


def ingest(url, upload, upload_name) -> dict:
    """Top-level dispatch — upload wins over URL if both provided."""
    if upload is not None:
        return ingest_upload(upload, upload_name or "audio.mp3")
    if not url:
        raise IngestError("No source provided.")
    if _is_youtube(url):
        return ingest_youtube(url)
    return ingest_direct_url(url)


# =============================================================================
# Transcribe — Gemini with content-hash cache
# =============================================================================

def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:24]


def _cache_path(audio_path: str, diarise: bool) -> Path:
    key = _file_hash(audio_path) + ("_diar" if diarise else "")
    return TMP_TRANSCRIPTS / f"{key}.json"


def _parse_diarised(text: str) -> tuple[str, int]:
    speakers: set[int] = set()
    lines: list[str] = []
    for line in text.strip().split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^Speaker\s+(\d+):\s*(.*)", stripped)
        if m:
            speakers.add(int(m.group(1)))
        lines.append(stripped)
    return "\n\n".join(lines), len(speakers)


def transcribe(audio_path: str, diarise: bool = False) -> dict:
    """Returns {"text": str, "speaker_count": int, "cached": bool}."""
    cache = _cache_path(audio_path, diarise)
    if cache.exists():
        return {**json.loads(cache.read_text()), "cached": True}

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise TranscribeError("GEMINI_API_KEY is not set.")

    try:
        client = genai.Client(api_key=api_key)
        uploaded = client.files.upload(file=audio_path)
        if diarise:
            prompt = (
                "Transcribe this audio exactly. Identify each speaker and label every turn as "
                "'Speaker 0: ...', 'Speaker 1: ...', etc. Output only the labelled transcript, "
                "no additional commentary."
            )
        else:
            prompt = (
                "Transcribe this audio exactly. Output only the transcript text with no "
                "additional commentary, labels, or formatting."
            )
        response = client.models.generate_content(
            model=TRANSCRIBE_MODEL,
            contents=[uploaded, prompt],
        )
        client.files.delete(name=uploaded.name)
        raw = response.text.strip()
    except Exception as e:
        raise TranscribeError(f"Gemini transcription failed: {e}") from e

    if diarise:
        text, speaker_count = _parse_diarised(raw)
    else:
        text, speaker_count = raw, 0

    out = {"text": text, "speaker_count": speaker_count}
    cache.write_text(json.dumps(out))
    return {**out, "cached": False}


# =============================================================================
# Summarise — streamed Gemini call
# =============================================================================

def stream_summary(
    transcript: str,
    title: str,
    source_url: str,
    duration_seconds: float,
    speaker_count,
    model: str = "gemini-2.5-pro",
) -> Iterator[str]:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SummariseError("GEMINI_API_KEY is not set.")

    prompt = build_prompt(transcript, title, source_url, duration_seconds, speaker_count)
    client = genai.Client(api_key=api_key)

    try:
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=prompt,
        ):
            if getattr(chunk, "text", None):
                yield chunk.text
    except Exception as e:
        raise SummariseError(f"Gemini failed: {e}") from e


# =============================================================================
# Streamlit UI helpers
# =============================================================================

def _filename_slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "").strip("_")[:60] or "podcast"


def _friendly_ingest_error(e: Exception) -> str:
    msg = str(e).lower()
    if "youtube" in msg:
        return ("YouTube didn't let me grab this one. Try uploading the audio "
                "file directly, or use a different URL.")
    if "too large" in msg or "exceeded" in msg:
        return f"That file is too large for the POC (limit 500 MB). {e}"
    if "unsupported" in msg:
        return "I couldn't recognise that audio format. Try mp3, wav, or m4a."
    if "no source" in msg:
        return "Provide a URL or upload an audio file."
    if "could not download" in msg or "404" in msg or "connection" in msg:
        return ("Couldn't download the audio — the source might be temporarily "
                "unavailable. Want to try again?")
    return f"Ingest failed: {e}"


# =============================================================================
# Streamlit app
# =============================================================================

st.set_page_config(page_title="Podcast Summariser", page_icon="🎙️", layout="centered")

if "runs" not in st.session_state:
    st.session_state.runs = []
if "active" not in st.session_state:
    st.session_state.active = None

# API-key sanity check
missing = []
if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
    missing.append("GEMINI_API_KEY (for transcription)")
if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
    missing.append("GEMINI_API_KEY")
if missing:
    st.error(f"Missing environment variables: {', '.join(missing)}. "
             f"Set them in your .env (see .env.example).")
    st.stop()

# Header
st.title("🎙️ Podcast Summariser")
st.caption("Paste a podcast URL or upload audio. Get a structured summary in "
           "under five minutes.")

# Sidebar: recent runs
with st.sidebar:
    st.subheader("Recent runs")
    if not st.session_state.runs:
        st.caption("Runs from this session will appear here.")
    recent = list(reversed(st.session_state.runs[-5:]))
    for offset, run in enumerate(recent):
        idx = len(st.session_state.runs) - 1 - offset
        label = f"{run['title'][:38]}  ·  {run['timestamp']}"
        if st.button(label, key=f"run_{idx}", use_container_width=True):
            st.session_state.active = run
            st.rerun()

# Input
st.subheader("📎 Source")
url_input = st.text_input(
    "Podcast URL (RSS episode link or YouTube)",
    placeholder="https://...",
)
st.caption("— or —")
uploaded = st.file_uploader(
    "Upload audio file",
    type=["mp3", "wav", "m4a", "mp4", "ogg", "flac"],
)
diarise = st.checkbox("Include speaker diarisation (slightly slower)", value=False)

st.caption(
    f"Rough cost: ~$0.45 (Flash) / ~$0.85 (Pro) per 90-min episode. "
    f"Current model: `{DEFAULT_MODEL}`. Exact estimate shown after fetch."
)

run_clicked = st.button("▶ Generate summary", type="primary", use_container_width=True)

# Run
if run_clicked:
    if not url_input and uploaded is None:
        st.error("Provide a URL or upload an audio file.")
        st.stop()

    run_record = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "title": "",
        "summary": "",
        "transcript": "",
        "metadata": {},
        "diarised": diarise,
        "model": DEFAULT_MODEL,
    }
    summary_buf: list[str] = []

    with st.status("Processing…", expanded=True) as status:
        # 1. Ingest
        st.write("📥 Fetching audio…")
        try:
            t0 = time.time()
            meta = ingest(
                url_input.strip() if url_input else None,
                uploaded,
                uploaded.name if uploaded else None,
            )
            t1 = time.time()
            duration_min = meta["duration_seconds"] / 60
            st.write(
                f"✅ Audio ready — **{meta['title']}** "
                f"({duration_min:.1f} min) in {t1 - t0:.1f}s"
            )
        except IngestError as e:
            status.update(label="Ingest failed", state="error")
            st.error(_friendly_ingest_error(e))
            st.stop()

        run_record["title"] = meta["title"]
        run_record["metadata"] = {
            "title": meta["title"],
            "source_url": meta["source_url"],
            "source_type": meta["source_type"],
            "duration_seconds": meta["duration_seconds"],
        }

        est = estimate_cost(meta["duration_seconds"], diarise, DEFAULT_MODEL)
        st.write(
            f"💰 Estimated cost: **${est['total_usd']:.2f}** "
            f"(Gemini ${est['gemini_usd']:.2f}) · "
            f"~{est['estimated_minutes']:.1f} min"
        )

        if meta["duration_seconds"] > 4 * 3600:
            st.warning(
                f"Long episode (~{meta['duration_seconds']/3600:.1f}h). "
                f"Continuing — but cost will scale roughly linearly."
            )

        # 2. Transcribe
        st.write("🎧 Transcribing with Gemini…")
        try:
            t0 = time.time()
            tr = transcribe(meta["path"], diarise=diarise)
            t1 = time.time()
            cached_note = " (cached)" if tr["cached"] else ""
            st.write(
                f"✅ Transcript ready ({len(tr['text'].split()):,} words) "
                f"in {t1 - t0:.1f}s{cached_note}"
            )
        except TranscribeError as e:
            status.update(label="Transcription failed", state="error")
            st.error(f"Transcription failed: {e}")
            st.stop()

        run_record["transcript"] = tr["text"]
        run_record["metadata"]["speaker_count"] = tr["speaker_count"]

        # 3. Summarise (streamed)
        st.write("✍️ Summarising with Gemini…")
        summary_placeholder = st.empty()

        try:
            for piece in stream_summary(
                transcript=tr["text"],
                title=meta["title"],
                source_url=meta["source_url"],
                duration_seconds=meta["duration_seconds"],
                speaker_count=tr["speaker_count"] or None,
                model=DEFAULT_MODEL,
            ):
                summary_buf.append(piece)
                summary_placeholder.markdown("".join(summary_buf))
        except SummariseError as e:
            status.update(label="Summarisation failed", state="error")
            st.error(f"Summarisation failed: {e}")
            st.stop()

        status.update(label="Done", state="complete")

    run_record["summary"] = "".join(summary_buf)
    st.session_state.runs.append(run_record)
    st.session_state.active = run_record

# Display active run
active = st.session_state.active
if active and active.get("summary"):
    st.divider()
    tab_summary, tab_transcript, tab_meta = st.tabs(
        ["📝 Summary", "📜 Transcript", "ℹ️ Metadata"]
    )

    with tab_summary:
        st.markdown(active["summary"])
        st.download_button(
            "⬇ Download as Markdown",
            data=active["summary"],
            file_name=f"{_filename_slug(active['title'])}_summary.md",
            mime="text/markdown",
        )

    with tab_transcript:
        st.text_area(
            "Transcript",
            active["transcript"],
            height=500,
            label_visibility="collapsed",
        )
        st.download_button(
            "⬇ Download transcript",
            data=active["transcript"],
            file_name=f"{_filename_slug(active['title'])}_transcript.txt",
            mime="text/plain",
        )

    with tab_meta:
        m = active["metadata"]
        st.write(f"**Title:** {m.get('title', '—')}")
        st.write(f"**Source:** {m.get('source_url', '—')}")
        st.write(f"**Type:** {m.get('source_type', '—')}")
        st.write(f"**Duration:** {m.get('duration_seconds', 0) / 60:.1f} minutes")
        if m.get("speaker_count"):
            st.write(f"**Speakers identified:** {m['speaker_count']}")
        st.write(f"**Diarisation:** {'on' if active.get('diarised') else 'off'}")
        st.write(f"**Summary model:** `{active.get('model', DEFAULT_MODEL)}`")
        st.write(f"**Run time:** {active.get('timestamp', '—')}")