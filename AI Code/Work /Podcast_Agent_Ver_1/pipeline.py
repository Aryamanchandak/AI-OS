"""Podcast pipeline — pure functions.

Each step (RSS → audio → transcript → summary → markdown) is a plain function with
no UI and no MCP coupling. `server.py` exposes these as MCP tools; they can also be
called directly for testing.

Source strategy: RSS first. If the latest RSS entry has no audio enclosure, the caller
falls back to `find_youtube_episode` (Gemini grounded search) → `ingest_youtube`.
"""
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
import yaml
from google import genai
from google.genai import types
from mutagen import File as MutagenFile

from config import (
    DEFAULT_MODEL,
    OUTPUT_SUMMARIES,
    OUTPUT_TRANSCRIPTS,
    PODCASTS_FILE,
    SEARCH_MODEL,
    SUMMARY_PROMPT,
    SUPPORTED_EXTS,
    TMP_AUDIO,
    TMP_TRANSCRIPTS,
    TRANSCRIBE_MODEL,
)

for d in (TMP_AUDIO, TMP_TRANSCRIPTS, OUTPUT_TRANSCRIPTS, OUTPUT_SUMMARIES):
    d.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Errors
# =============================================================================

class IngestError(Exception):
    pass


class TranscribeError(Exception):
    pass


class SummariseError(Exception):
    pass


class RSSError(Exception):
    pass


class YouTubeSearchError(Exception):
    pass


# =============================================================================
# Gemini client
# =============================================================================

def _gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key.startswith("your_"):
        raise TranscribeError("GEMINI_API_KEY is not set in .env")
    return genai.Client(api_key=api_key)


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

    Returns: {title, published, duration_seconds, audio_url}
    `audio_url` is None when no audio enclosure exists (caller should try YouTube).
    """
    feed = feedparser.parse(rss_url)
    if feed.bozo and not feed.entries:
        raise RSSError(f"Could not parse RSS feed: {rss_url}")
    if not feed.entries:
        raise RSSError("RSS feed has no episodes.")

    entry = feed.entries[0]
    title = entry.get("title", "Untitled episode")

    # Audio URL is usually in enclosures
    audio_url = None
    for enc in entry.get("enclosures", []):
        mime = enc.get("type", "")
        if "audio" in mime or enc.get("url", "").lower().endswith(
            (".mp3", ".m4a", ".wav", ".ogg", ".aac")
        ):
            audio_url = enc["url"]
            break

    # Fallback: links
    if not audio_url:
        for link in entry.get("links", []):
            if "audio" in link.get("type", "") or link.get("rel") == "enclosure":
                audio_url = link["href"]
                break

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

    return {
        "title": title,
        "published": entry.get("published", ""),
        "duration_seconds": duration_seconds,
        "audio_url": audio_url,
    }


# =============================================================================
# YouTube discovery (Gemini grounded search)
# =============================================================================

_YT_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+)"
)


def find_youtube_episode(podcast_name: str, episode_title: str = "") -> dict:
    """Use Gemini's google_search grounding to find the latest episode on YouTube.

    Returns {url, query}. Raises YouTubeSearchError if no parseable watch URL is found.
    """
    client = _gemini_client()
    target = f'the podcast "{podcast_name}"'
    if episode_title:
        target += f', specifically the episode titled "{episode_title}"'
    prompt = (
        f"Find the official YouTube video for the latest episode of {target}. "
        "Return ONLY the full watch URL on its own line, in the form "
        "https://www.youtube.com/watch?v=VIDEOID — no other text."
    )
    try:
        resp = client.models.generate_content(
            model=SEARCH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = resp.text or ""
    except Exception as e:
        raise YouTubeSearchError(f"Gemini grounded search failed: {e}") from e

    # Primary: parse a watch URL straight out of the model's answer.
    match = _YT_RE.search(text)
    # Fallback: grounding metadata often carries the real source URLs.
    if not match:
        try:
            for cand in resp.candidates or []:
                gm = getattr(cand, "grounding_metadata", None)
                for chunk in getattr(gm, "grounding_chunks", []) or []:
                    uri = getattr(getattr(chunk, "web", None), "uri", "") or ""
                    match = _YT_RE.search(uri)
                    if match:
                        break
                if match:
                    break
        except Exception:
            pass

    if not match:
        raise YouTubeSearchError(
            f"Could not find a YouTube URL for {podcast_name!r}. Model said: {text[:200]!r}"
        )
    return {"url": match.group(0), "query": prompt}


# =============================================================================
# Ingest
# =============================================================================

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
        with requests.get(url, stream=True, timeout=60) as r:
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


def download_audio(url: str) -> dict:
    """Route a URL to the right ingest function (YouTube vs direct enclosure)."""
    host = urlparse(url).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return ingest_youtube(url)
    return ingest_direct_url(url)


# =============================================================================
# Transcribe (Gemini, with on-disk cache keyed by file hash)
# =============================================================================

def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:24]


def transcribe(audio_path: str) -> dict:
    """Transcribe audio with Gemini. Returns {text, cached}."""
    cache = TMP_TRANSCRIPTS / f"{_file_hash(audio_path)}.json"
    if cache.exists():
        return {**json.loads(cache.read_text()), "cached": True}

    client = _gemini_client()
    prompt = (
        "Transcribe this audio exactly. At the start of each new paragraph or natural "
        "pause, insert a timestamp in [HH:MM:SS] format indicating when that segment "
        "begins in the audio. Output only the timestamped transcript, no other commentary."
    )
    try:
        uploaded = client.files.upload(file=audio_path)
        response = client.models.generate_content(
            model=TRANSCRIBE_MODEL,
            contents=[uploaded, prompt],
        )
        client.files.delete(name=uploaded.name)
        text = (response.text or "").strip()
    except Exception as e:
        raise TranscribeError(f"Gemini transcription failed: {e}") from e

    out = {"text": text}
    cache.write_text(json.dumps(out))
    return {**out, "cached": False}


# =============================================================================
# Summarise (Gemini)
# =============================================================================

def _human_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m" if h else f"{m}m"


def summarise(
    transcript: str,
    title: str,
    source_url: str,
    duration_seconds: float = 0.0,
    model: str = DEFAULT_MODEL,
) -> str:
    if not transcript.strip():
        raise SummariseError("Cannot summarise an empty transcript.")
    # Use replace (not str.format) so braces inside the transcript can't break templating.
    prompt = (
        SUMMARY_PROMPT
        .replace("{title}", title or "Untitled episode")
        .replace("{source_url}", source_url or "Unknown")
        .replace("{duration_human}", _human_duration(duration_seconds))
        .replace("{speaker_count_line}", "")
        .replace("{transcript}", transcript)
    )
    client = _gemini_client()
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        return (resp.text or "").strip()
    except Exception as e:
        raise SummariseError(f"Gemini summarisation failed: {e}") from e


# =============================================================================
# Output helpers
# =============================================================================

def output_slug(podcast_name: str, episode_title: str) -> str:
    date = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = re.sub(r"[^A-Za-z0-9]+", "_", podcast_name).strip("_")[:30]
    title = re.sub(r"[^A-Za-z0-9]+", "_", episode_title).strip("_")[:50]
    return f"{date}_{name}_{title}"


def _write_md(path: Path, episode_title: str, podcast_name: str, body: str) -> Path:
    path.write_text(
        f"# {episode_title}\n\n**Podcast:** {podcast_name}  \n"
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n\n---\n\n{body}"
    )
    return path


def save_outputs(
    podcast_name: str, episode_title: str, transcript: str, summary: str
) -> dict:
    """Persist transcript + summary as markdown. Returns saved paths and slug."""
    slug = output_slug(podcast_name, episode_title)
    t_path = _write_md(
        OUTPUT_TRANSCRIPTS / f"{slug}_transcript.md", episode_title, podcast_name, transcript
    )
    s_path = _write_md(
        OUTPUT_SUMMARIES / f"{slug}_summary.md", episode_title, podcast_name, summary
    )
    return {
        "slug": slug,
        "transcript_path": str(t_path),
        "summary_path": str(s_path),
    }
