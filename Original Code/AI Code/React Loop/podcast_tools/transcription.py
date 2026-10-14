"""Transcription entry points.

Deepgram handles audio. YouTube uses captions first and falls back to audio download
plus Deepgram when captions are unavailable.
"""

from __future__ import annotations

import html
import mimetypes
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from .ingestion import download_podcast_audio
from .storage import make_episode_id, require_env, write_transcript

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
DEFAULT_CAPTION_LANGUAGES = ("en", "en-US", "en-GB", "en-CA", "en-AU")


def transcribe_audio(file_path: str) -> str:
    """Transcribe a local audio file with Deepgram and return raw transcript text."""
    import httpx

    api_key = require_env("DEEPGRAM_API_KEY")
    audio_path = Path(file_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    content_type = mimetypes.guess_type(str(audio_path))[0] or "audio/mpeg"
    params = {
        "model": "nova-3",
        "diarize": "true",
        "smart_format": "true",
        "punctuate": "true",
        "paragraphs": "true",
    }
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": content_type,
    }

    with audio_path.open("rb") as audio:
        response = httpx.post(
            DEEPGRAM_URL,
            params=params,
            headers=headers,
            content=audio,
            timeout=900,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Deepgram error {response.status_code}: {response.text[:500]}")

    return _extract_deepgram_transcript(response.json())


def transcribe_source(
    source_url: str,
    title: str = "",
    episode_id: Optional[str] = None,
    platform: Optional[str] = None,
    prefer_captions: bool = True,
) -> str:
    """Transcribe an RSS audio URL or YouTube URL, save markdown, and return the path."""
    resolved_id = episode_id or make_episode_id(source_url)
    resolved_platform = platform or ("youtube" if _is_youtube_url(source_url) else "rss")

    # Prefer a real title over the ugly episode_id so transcript/summary headers read well.
    if not title.strip() and resolved_platform == "youtube":
        title = _fetch_youtube_title(source_url)

    transcript = ""
    if prefer_captions and resolved_platform == "youtube":
        transcript = fetch_youtube_captions(source_url)

    if not transcript:
        audio_path = download_podcast_audio(source_url, title=title)
        transcript = transcribe_audio(audio_path)

    if not transcript.strip():
        raise RuntimeError("Transcription produced an empty transcript.")

    return write_transcript(
        episode_id=resolved_id,
        transcript=transcript,
        title=title,
        source_url=source_url,
        platform=resolved_platform,
    )


def transcribe_youtube(
    youtube_url: str,
    title: str = "",
    prefer_captions: bool = True,
) -> str:
    """Transcribe one YouTube video and save ``data/transcripts/<episode_id>.md``."""
    return transcribe_source(
        youtube_url,
        title=title,
        platform="youtube",
        prefer_captions=prefer_captions,
    )


def fetch_youtube_captions(
    youtube_url: str,
    languages: Iterable[str] = DEFAULT_CAPTION_LANGUAGES,
) -> str:
    """Return YouTube captions text, or an empty string if captions are unavailable."""
    video_id = _extract_youtube_video_id(youtube_url)
    if not video_id:
        return ""

    transcript = _fetch_captions_with_api(video_id, languages)
    if not transcript:
        transcript = _fetch_captions_with_ytdlp(youtube_url)
    # Captions arrive as one long run-on string; give them real paragraph structure
    # so chunking and the summariser see coherent units instead of a wall of text.
    return _paragraphize(transcript)


def _extract_deepgram_transcript(payload: dict) -> str:
    alternative = (
        payload.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
    )

    paragraphs = alternative.get("paragraphs") or {}
    paragraph_transcript = paragraphs.get("transcript")
    if paragraph_transcript:
        return paragraph_transcript.strip()

    words = alternative.get("words") or []
    if words:
        return _format_diarized_words(words)

    return (alternative.get("transcript") or "").strip()


def _format_diarized_words(words: list[dict]) -> str:
    lines = []
    current_speaker = None
    current_words = []

    for word in words:
        speaker = word.get("speaker")
        token = word.get("punctuated_word") or word.get("word") or ""
        if not token:
            continue
        if speaker != current_speaker and current_words:
            lines.append(_speaker_line(current_speaker, current_words))
            current_words = []
        current_speaker = speaker
        current_words.append(token)

    if current_words:
        lines.append(_speaker_line(current_speaker, current_words))
    return "\n\n".join(lines).strip()


def _speaker_line(speaker: object, words: list[str]) -> str:
    label = "Speaker" if speaker is None else f"Speaker {speaker}"
    return f"{label}: {' '.join(words)}"


def _fetch_captions_with_api(video_id: str, languages: Iterable[str]) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return ""

    try:
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            entries = YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))
        else:
            entries = YouTubeTranscriptApi().fetch(video_id, languages=list(languages))
    except Exception:
        return ""

    texts = []
    for entry in entries:
        text = getattr(entry, "text", None)
        if text is None and isinstance(entry, dict):
            text = entry.get("text", "")
        if text:
            texts.append(_clean_caption_text(text))
    return _join_caption_lines(texts)


def _fetch_captions_with_ytdlp(youtube_url: str) -> str:
    with tempfile.TemporaryDirectory() as temp_dir:
        output_template = str(Path(temp_dir) / "captions.%(ext)s")
        cmd = [
            "yt-dlp",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "en.*",
            "--sub-format",
            "vtt",
            "--skip-download",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "-o",
            output_template,
            youtube_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return ""

        caption_files = sorted(Path(temp_dir).glob("*.vtt"))
        if not caption_files:
            return ""
        return _parse_vtt(caption_files[0].read_text(encoding="utf-8", errors="ignore"))


def _parse_vtt(raw_vtt: str) -> str:
    lines = []
    for raw_line in raw_vtt.splitlines():
        line = raw_line.strip()
        if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        if "-->" in line or line.isdigit():
            continue
        lines.append(_clean_caption_text(line))
    return _join_caption_lines(lines)


def _clean_caption_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _join_caption_lines(lines: Iterable[str]) -> str:
    cleaned = []
    previous = ""
    for line in lines:
        if not line or line == previous:
            continue
        cleaned.append(line)
        previous = line
    return " ".join(cleaned).strip()


def _paragraphize(text: str, sentences_per_paragraph: int = 5) -> str:
    """Regroup a run-on caption string into readable paragraphs.

    Splits on sentence-ending punctuation and gathers a handful of sentences per
    paragraph separated by blank lines, so downstream chunking and the summariser
    see coherent units. Returns the input unchanged when there is nothing to split.
    """
    text = text.strip()
    if not text:
        return ""

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) <= 1:
        return text

    paragraphs = [
        " ".join(sentences[i:i + sentences_per_paragraph])
        for i in range(0, len(sentences), sentences_per_paragraph)
    ]
    return "\n\n".join(paragraphs)


def _fetch_youtube_title(youtube_url: str) -> str:
    """Best-effort fetch of a video's real title via yt-dlp. Empty string on failure."""
    cmd = [
        "yt-dlp",
        "--print", "%(title)s",
        "--skip-download",
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        youtube_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""


def _is_youtube_url(url: str) -> bool:
    return bool(_extract_youtube_video_id(url))


def _extract_youtube_video_id(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", url)
    return match.group(1) if match else ""
