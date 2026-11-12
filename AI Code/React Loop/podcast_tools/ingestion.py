"""RSS and YouTube podcast ingestion: list episodes and download audio.

Self-contained by design: no MCP server, no database, no provenance logging.
Optional runtime dependencies are loaded inside the functions that need them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import urlparse

from .feeds import resolve_feed
from .storage import AUDIO_DIR, ensure_dirs, make_episode_id

_AUDIO_SUFFIXES = (".mp3", ".m4a", ".ogg", ".wav", ".aac")


def _looks_like_direct_audio(url: str) -> bool:
    return urlparse(url).path.lower().endswith(_AUDIO_SUFFIXES)


def _find_audio_url(entry: dict) -> str:
    # Prefer explicitly audio-typed links/enclosures.
    for link in entry.get("links", []):
        if link.get("type", "").startswith("audio"):
            return link.get("href", "")
    for enclosure in entry.get("enclosures", []):
        if "audio" in enclosure.get("type", ""):
            return enclosure.get("url") or enclosure.get("href") or ""
    # Fall back for feeds that omit the type: any enclosure with a URL, or any link
    # whose href points at an audio file. Better than dropping a valid episode.
    for enclosure in entry.get("enclosures", []):
        candidate = enclosure.get("url") or enclosure.get("href") or ""
        if candidate:
            return candidate
    for link in entry.get("links", []):
        href = link.get("href", "")
        if _looks_like_direct_audio(href):
            return href
    return ""


def list_rss_episodes(rss_url: str, limit: int = 5) -> list[dict]:
    """Fetch and normalize the latest entries from a podcast RSS feed.

    ``rss_url`` may be a raw RSS URL or a curated feed name (e.g. ``"dwarkesh"``,
    ``"joe rogan"``) — see ``feeds.txt``.
    """
    import feedparser

    rss_url = resolve_feed(rss_url)
    feed = feedparser.parse(rss_url)
    results: list[dict] = []
    for entry in feed.entries[:limit]:
        audio_url = _find_audio_url(entry)
        if not audio_url:
            continue
        results.append({
            "episode_id": make_episode_id(audio_url),
            "title": entry.get("title", "Unknown"),
            "source_url": audio_url,
            "platform": "rss",
            "published": entry.get("published", ""),
            "description": str(entry.get("summary", ""))[:500],
        })
    return results


def list_youtube_channel_episodes(channel_id: str, limit: int = 5) -> list[dict]:
    """List the latest videos from a YouTube channel using yt-dlp."""
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
        raise RuntimeError(result.stderr.strip() or "yt-dlp failed to list channel videos")

    episodes: list[dict] = []
    for raw_line in result.stdout.splitlines():
        if "|||" not in raw_line:
            continue
        video_id, title = raw_line.split("|||", 1)
        video_id = video_id.strip()
        episodes.append({
            "episode_id": f"yt_{video_id}",
            "title": title.strip() or video_id,
            "source_url": f"https://www.youtube.com/watch?v={video_id}",
            "platform": "youtube",
        })
    return episodes


def download_podcast_audio(url: str, title: str = "") -> str:
    """Download podcast audio (RSS direct or YouTube) to a local MP3. Returns the file path."""
    ensure_dirs()
    episode_id = make_episode_id(url)
    out_path = AUDIO_DIR / f"{episode_id}.mp3"

    if out_path.exists() and out_path.stat().st_size > 1024:
        return str(out_path)

    if _looks_like_direct_audio(url):
        _download_direct(url, out_path)
    else:
        _download_ytdlp(url, out_path)

    return str(out_path)


def _download_direct(url: str, out_path: Path) -> None:
    import httpx

    with httpx.stream("GET", url, timeout=120, headers={"User-Agent": "Mozilla/5.0"},
                      follow_redirects=True) as response:
        response.raise_for_status()
        with out_path.open("wb") as handle:
            for chunk in response.iter_bytes(chunk_size=65536):
                handle.write(chunk)


def _download_ytdlp(url: str, out_path: Path) -> None:
    output_template = str(out_path.with_suffix("")) + ".%(ext)s"
    cmd = [
        "yt-dlp", "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--no-playlist",
        "--quiet", "--no-warnings",
        "-o", output_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr.strip()}")

    if not out_path.exists():
        for candidate in out_path.parent.glob(f"{out_path.stem}*"):
            if candidate.suffix.lower() == ".mp3" and candidate != out_path:
                candidate.rename(out_path)
                break
