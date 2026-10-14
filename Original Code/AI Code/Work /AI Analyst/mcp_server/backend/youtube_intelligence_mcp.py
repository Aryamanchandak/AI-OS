import os
import re

import yt_dlp
from google import genai
from mcp.server.fastmcp import FastMCP
from pytubefix import YouTube

mcp = FastMCP("youtube")

MODEL = "gemini-3-flash-preview"


@mcp.tool()
def search_youtube(query: str) -> list[dict]:
    """
    Search YouTube for videos matching a query.
    Returns up to 40 results, each with:
      title, url, channel, view_count, duration, thumbnail
    Use this before summarize_youtube_video to find the right video URL.
    """
    if not query or not query.strip():
        raise ValueError("query cannot be empty.")

    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        results = ydl.extract_info(f"ytsearch40:{query}", download=False)

    videos = []
    for entry in results["entries"]:
        video_id = entry.get("id")
        videos.append({
            "title": entry.get("title"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "channel": entry.get("uploader"),
            "view_count": entry.get("view_count"),
            "duration": entry.get("duration"),
            "thumbnail": (
                entry.get("thumbnail")
                or f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            ),
        })

    return videos


@mcp.tool()
def fetch_youtube_transcript(url: str) -> str:
    """
    Fetch and clean the transcript from a YouTube video URL.
    Returns plain text transcript.
    Raises ValueError if captions are unavailable (auto-generated or private video).
    Use this before summarize_transcript, or standalone to inspect transcript length
    or language before deciding whether to summarise.
    """
    if not url or "youtube.com" not in url:
        raise ValueError(f"Invalid YouTube URL: {url!r}")

    yt = YouTube(url)

    if not yt.captions:
        raise ValueError(
            f"No transcript available for {url}. "
            "The video may have captions disabled or be private."
        )

    first_caption = list(yt.captions.keys())[0]
    caption = yt.captions.get(first_caption.code)
    srt = caption.generate_srt_captions()

    plain = re.sub(r"\d+\n\d{2}:\d{2}:\d{2},\d{3} --> .*?\n", "", srt)
    transcript = re.sub(r"\n+", " ", plain).strip()

    if not transcript:
        raise ValueError(
            f"No transcript available for {url}. "
            "The video may have captions disabled or be private."
        )

    return transcript


@mcp.tool()
def summarize_transcript(transcript: str) -> str:
    """
    Generate an investment-analyst-style summary from a video transcript.
    Input: plain text transcript from fetch_youtube_transcript or any source.
    Returns structured markdown summary covering key points, data cited,
    investment relevance, and notable quotes.
    """
    if not transcript or not transcript.strip():
        raise ValueError("transcript cannot be empty.")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set.")

    client = genai.Client(api_key=api_key)

    prompt = f"""You are an expert equity research analyst.

Summarize the following video transcript in a structured, insightful, and
investment-relevant manner suitable for fund managers and institutional analysts.

Transcript:
{transcript}"""

    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
    except Exception as e:
        raise RuntimeError(f"summarize_transcript: Gemini call failed. {e}") from e

    return response.text


@mcp.tool()
def summarize_youtube_video(url: str) -> str:
    """
    Fetch the transcript from a YouTube URL and generate an analyst-style summary.
    Returns structured markdown.
    Use search_youtube first to find relevant videos, then call this with the URL.
    Use component tools individually if you need the raw transcript or want to
    summarise a transcript from a non-YouTube source.
    """
    transcript = fetch_youtube_transcript(url)
    return summarize_transcript(transcript)
