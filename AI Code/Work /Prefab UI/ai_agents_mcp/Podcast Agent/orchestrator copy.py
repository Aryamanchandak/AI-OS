"""Podcast pipeline orchestrator.

Handles everything from RSS → audio → transcript → summary → .md output.
Importable by app.py (Streamlit) or runnable directly as a CLI script.
"""
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

import feedparser
import requests
import yaml
from google import genai
from mutagen import File as MutagenFile

from config import (
    DEFAULT_MODEL,
    MAX_BYTES,
    OUTPUT_SUMMARIES,
    OUTPUT_TRANSCRIPTS,
    PODCASTS_FILE,
    SUMMARY_COST_DEFAULT,
    SUMMARY_COST_PER_90_MIN,
    SUMMARY_PROMPT,
    SUPPORTED_EXTS,
    TRANSCRIBE_COST_PER_M_TOKENS,
    TRANSCRIBE_MODEL,
    TRANSCRIBE_TOKENS_PER_SEC,
    TMP_AUDIO,
    TMP_TRANSCRIPTS,
)

for d in (TMP_AUDIO, TMP_TRANSCRIPTS, OUTPUT_TRANSCRIPTS, OUTPUT_SUMMARIES):
    d.mkdir(parents=True, exist_ok=True)


class IngestError(Exception):
    pass


class TranscribeError(Exception):
    pass


class SummariseError(Exception):
    pass


class RSSError(Exception):
    pass


# =============================================================================
# Podcast list
# =============================================================================

def load_podcasts() -> list[dict]:
    """Read podcasts.yaml and return list of {name, rss} dicts."""
    if not PODCASTS_FILE.exists():
        return []
    with open(PODCASTS_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("podcasts", [])


# =============================================================================
# RSS
# =============================================================================

def get_latest_episode(rss_url: str) -> dict:
    """Parse RSS feed and return metadata for the latest episode.

    Returns: {url, title, published, duration_seconds}
    """
    feed = feedparser.parse(rss_url)
    if feed.bozo and not feed.entries:
        raise RSSError(f"Could not parse RSS feed: {rss_url}")
    if not feed.entries:
        raise RSSError("RSS feed has no episodes.")

    entry = feed.entries[0]
    title = entry.get("title", "Untitled episode")

    # Audio URL is usually in enclosures
    url = None
    for enc in entry.get("enclosures", []):
        mime = enc.get("type", "")
        if "audio" in mime or enc.get("url", "").lower().endswith(
            (".mp3", ".m4a", ".wav", ".ogg", ".aac")
        ):
            url = enc["url"]
            break

    # Fallback: links
    if not url:
        for link in entry.get("links", []):
            if "audio" in link.get("type", "") or link.get("rel") == "enclosure":
                url = link["href"]
                break

    if not url:
        raise RSSError(f"No audio enclosure found in latest episode: {title!r}")

    # Duration from itunes:duration tag (may be "HH:MM:SS" or seconds)
    duration_seconds = 0.0
    raw_dur = entry.get("itunes_duration", "") or ""
    if raw_dur:
        parts = str(raw_dur).split(":")
        try:
            if len(parts) == 3:
                duration_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                duration_seconds = int(parts[0]) * 60 + float(parts[1])
            else:
                duration_seconds = float(raw_dur)
        except ValueError:
            pass

    published = entry.get("published", "")

    return {
        "url": url,
        "title": title,
        "published": published,
        "duration_seconds": duration_seconds,
    }


# =============================================================================
# Cost estimation
# =============================================================================

def estimate_cost(duration_seconds: float, diarise: bool, model: str) -> dict:
    minutes = max(duration_seconds / 60, 0.0)
    transcription = TRANSCRIBE_COST_PER_M_TOKENS * TRANSCRIBE_TOKENS_PER_SEC * 60 * minutes / 1_000_000
    cost_per_90 = SUMMARY_COST_PER_90_MIN.get(model, SUMMARY_COST_DEFAULT)
    gemini = transcription + cost_per_90 * (minutes / 90)
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

def _human_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m" if h else f"{m}m"


def build_prompt(transcript, title, source_url, duration_seconds, speaker_count):
    return SUMMARY_PROMPT.format(
        title=title or "Untitled episode",
        source_url=source_url or "Unknown",
        duration_human=_human_duration(duration_seconds),
        speaker_count_line=(
            f"- Speakers identified: {speaker_count}" if speaker_count else ""
        ),
        transcript=transcript,
    )


# =============================================================================
# Ingest
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
        raise IngestError("yt-dlp is not installed. Run: pip install yt-dlp") from e

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

            with open(audio_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
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


# =============================================================================
# Transcribe
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
        m = re.match(r"^(?:\[\d{2}:\d{2}:\d{2}\]\s*)?Speaker\s+(\d+):\s*(.*)", stripped)
        if m:
            speakers.add(int(m.group(1)))
        lines.append(stripped)
    return "\n\n".join(lines), len(speakers)


def transcribe(audio_path: str, diarise: bool = False) -> dict:
    """Returns {text, speaker_count, cached}."""
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
                "Transcribe this audio exactly. Identify each speaker. Format every speaker turn as "
                "'[HH:MM:SS] Speaker N: ...' where [HH:MM:SS] is the timestamp when that turn "
                "begins in the audio. Output only the labelled transcript, no other commentary."
            )
        else:
            prompt = (
                "Transcribe this audio exactly. At the start of each new paragraph or natural "
                "pause, insert a timestamp in [HH:MM:SS] format indicating when that segment "
                "begins in the audio. Output only the timestamped transcript, no other commentary."
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
# Summarise
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
        for chunk in client.models.generate_content_stream(model=model, contents=prompt):
            if getattr(chunk, "text", None):
                yield chunk.text
    except Exception as e:
        raise SummariseError(f"Gemini failed: {e}") from e


# =============================================================================
# Output helpers
# =============================================================================

def _output_slug(podcast_name: str, episode_title: str) -> str:
    date = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = re.sub(r"[^A-Za-z0-9]+", "_", podcast_name).strip("_")[:30]
    title = re.sub(r"[^A-Za-z0-9]+", "_", episode_title).strip("_")[:50]
    return f"{date}_{name}_{title}"


def save_transcript(slug: str, podcast_name: str, episode_title: str, text: str) -> Path:
    path = OUTPUT_TRANSCRIPTS / f"{slug}_transcript.md"
    path.write_text(
        f"# {episode_title}\n\n**Podcast:** {podcast_name}  \n"
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n\n---\n\n{text}"
    )
    return path


def save_summary(slug: str, podcast_name: str, episode_title: str, text: str) -> Path:
    path = OUTPUT_SUMMARIES / f"{slug}_summary.md"
    path.write_text(
        f"# {episode_title}\n\n**Podcast:** {podcast_name}  \n"
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n\n---\n\n{text}"
    )
    return path


# =============================================================================
# Main pipeline callable
# =============================================================================

def run(
    podcast_name: str,
    rss_url: str,
    diarise: bool = False,
    model: str = DEFAULT_MODEL,
    upload=None,
    upload_name: str = "",
    progress_callback=None,
    on_chunk=None,
) -> dict:
    """Run the full pipeline and return a result dict.

    on_chunk(text: str) is called for each streamed summary chunk so callers
    can render output progressively without owning any pipeline logic.
    progress_callback(step: str, detail: str) is called at each pipeline stage.
    """
    def _progress(step, detail=""):
        if progress_callback:
            progress_callback(step, detail)

    result = {
        "podcast_name": podcast_name,
        "episode_title": "",
        "transcript_path": None,
        "summary_path": None,
        "summary_text": "",
        "transcript_text": "",
        "metadata": {},
    }

    # 1. Resolve source
    if upload is not None:
        _progress("ingest", "Uploading audio…")
        meta = ingest_upload(upload, upload_name or "audio.mp3")
        meta["title"] = meta["title"] or podcast_name
    else:
        _progress("rss", f"Fetching RSS for {podcast_name}…")
        episode = get_latest_episode(rss_url)
        result["episode_title"] = episode["title"]
        _progress("ingest", f"Downloading: {episode['title']}")
        episode_url = episode["url"]
        if _is_youtube(episode_url):
            meta = ingest_youtube(episode_url)
        else:
            meta = ingest_direct_url(episode_url)
        meta["title"] = episode["title"]
        if episode["duration_seconds"]:
            meta["duration_seconds"] = episode["duration_seconds"]

    result["episode_title"] = result["episode_title"] or meta["title"]
    slug = _output_slug(podcast_name, result["episode_title"])

    result["metadata"] = {
        "title": meta["title"],
        "source_url": meta["source_url"],
        "source_type": meta["source_type"],
        "duration_seconds": meta["duration_seconds"],
        "podcast_name": podcast_name,
        "model": model,
        "diarised": diarise,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    # 2. Transcribe
    _progress("transcribe", "Transcribing with Gemini…")
    tr = transcribe(meta["path"], diarise=diarise)
    result["transcript_text"] = tr["text"]
    result["metadata"]["speaker_count"] = tr["speaker_count"]
    result["metadata"]["transcript_cached"] = tr["cached"]

    transcript_path = save_transcript(slug, podcast_name, result["episode_title"], tr["text"])
    result["transcript_path"] = str(transcript_path)

    # 3. Summarise — collect chunks; call on_chunk for streaming
    _progress("summarise", "Summarising with Gemini…")
    chunks = []
    for chunk in stream_summary(
        transcript=tr["text"],
        title=meta["title"],
        source_url=meta["source_url"],
        duration_seconds=meta["duration_seconds"],
        speaker_count=tr["speaker_count"] or None,
        model=model,
    ):
        chunks.append(chunk)
        if on_chunk:
            on_chunk(chunk)

    summary_text = "".join(chunks)
    result["summary_text"] = summary_text

    summary_path = save_summary(slug, podcast_name, result["episode_title"], summary_text)
    result["summary_path"] = str(summary_path)

    return result


# =============================================================================
# CLI entry point
# =============================================================================

if __name__ == "__main__":
    import sys

    podcasts = load_podcasts()
    if not podcasts:
        print("No podcasts in podcasts.yaml")
        sys.exit(1)

    print("Available podcasts:")
    for i, p in enumerate(podcasts):
        print(f"  {i + 1}. {p['name']}")

    choice = input("\nPick a number: ").strip()
    try:
        idx = int(choice) - 1
        selected = podcasts[idx]
    except (ValueError, IndexError):
        print("Invalid choice.")
        sys.exit(1)

    print(f"\nRunning pipeline for: {selected['name']}")
    result = run(
        selected["name"],
        selected["rss"],
        progress_callback=lambda s, d: print(f"[{s}] {d}"),
        on_chunk=lambda c: print(c, end="", flush=True),
    )
    print(f"\nDone.")
    print(f"  Transcript: {result['transcript_path']}")
    print(f"  Summary:    {result['summary_path']}")
