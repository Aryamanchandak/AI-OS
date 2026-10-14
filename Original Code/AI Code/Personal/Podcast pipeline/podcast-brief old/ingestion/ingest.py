"""
ingest.py — Fetch audio from YouTube URLs, direct MP3 links, or RSS feeds.
"""

import re
import hashlib
import subprocess
import feedparser
import requests
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

from core.config import AUDIO_DIR, ensure_dirs
from core.models import EpisodeInfo, RSSEpisode


# ─── Episode ID derivation ──────────────────────────────────────────────────

def make_episode_id(url: str) -> str:
    """Derive a stable, unique episode ID from a URL."""
    yt_match = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", url)
    if yt_match:
        return f"yt_{yt_match.group(1)}"
    return "ep_" + hashlib.md5(url.encode()).hexdigest()[:12]


# ─── Single-URL fetching ─────────────────────────────────────────────────────

def fetch_audio(url: str, title: str = "") -> EpisodeInfo:
    """Download audio from a URL. Caches by episode ID — won't re-download."""
    ensure_dirs()

    episode_id = make_episode_id(url)
    out_path = AUDIO_DIR / f"{episode_id}.mp3"

    if out_path.exists() and out_path.stat().st_size > 1024:
        return EpisodeInfo(
            id=episode_id,
            title=title or _ytdlp_title(url) or episode_id,
            source_url=url,
            audio_path=out_path,
        )

    parsed = urlparse(url)
    if parsed.path.lower().endswith((".mp3", ".m4a", ".ogg", ".wav", ".aac")):
        _download_direct(url, out_path)
    else:
        _download_ytdlp(url, out_path)

    return EpisodeInfo(
        id=episode_id,
        title=title or _ytdlp_title(url) or episode_id,
        source_url=url,
        audio_path=out_path,
    )


def _download_direct(url: str, out_path: Path):
    """Stream-download a direct audio URL."""
    response = requests.get(url, stream=True, timeout=120,
                            headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)


def _download_ytdlp(url: str, out_path: Path):
    """Use yt-dlp for YouTube and most podcast hosts."""
    # yt-dlp adds extensions automatically; provide the stem and let it append
    output_template = str(out_path.with_suffix("")) + ".%(ext)s"

    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "-o", output_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr.strip()}")

    # yt-dlp may produce different extensions before re-encoding; locate the mp3
    if not out_path.exists():
        for candidate in out_path.parent.glob(f"{out_path.stem}*"):
            if candidate.suffix.lower() == ".mp3":
                if candidate != out_path:
                    candidate.rename(out_path)
                break


def _ytdlp_title(url: str) -> Optional[str]:
    """Fetch episode title without downloading."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--print", "title", "--no-playlist", "--no-warnings", url],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


# ─── RSS polling ─────────────────────────────────────────────────────────────

def get_latest_rss_episodes(rss_url: str, limit: int = 5) -> list[RSSEpisode]:
    """Fetch latest episodes from an RSS feed."""
    feed = feedparser.parse(rss_url)
    episodes = []

    for entry in feed.entries[:limit]:
        audio_url = None

        # Try links first
        for link in entry.get("links", []):
            if link.get("type", "").startswith("audio"):
                audio_url = link.get("href")
                break

        # Then enclosures
        if not audio_url:
            for enc in entry.get("enclosures", []):
                if "audio" in enc.get("type", ""):
                    audio_url = enc.get("url") or enc.get("href")
                    break

        if not audio_url:
            continue

        episodes.append(RSSEpisode(
            guid=entry.get("id") or entry.get("link") or audio_url,
            title=entry.get("title", "Unknown"),
            audio_url=audio_url,
            published=entry.get("published", ""),
            description=str(entry.get("summary", ""))[:500],
        ))

    return episodes


# ─── YouTube channel polling ─────────────────────────────────────────────────

def get_latest_youtube_episodes(channel_id: str, limit: int = 5) -> list[dict]:
    """Latest videos from a YouTube channel via yt-dlp."""
    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
    cmd = [
        "yt-dlp",
        "--print", "%(id)s|||%(title)s",
        "--playlist-end", str(limit),
        "--no-download",
        "--no-warnings",
        "--quiet",
        channel_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return []

    episodes = []
    for line in result.stdout.strip().split("\n"):
        if "|||" not in line:
            continue
        vid_id, title = line.split("|||", 1)
        vid_id = vid_id.strip()
        episodes.append({
            "id": f"yt_{vid_id}",
            "title": title.strip(),
            "url": f"https://www.youtube.com/watch?v={vid_id}",
        })
    return episodes
