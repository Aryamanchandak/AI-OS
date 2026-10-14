"""MCP adapter for the pure podcast_tools library."""

from __future__ import annotations

import json

from podcast_tools import (
    ask_episode,
    list_feeds,
    list_rss_episodes,
    list_youtube_channel_episodes,
    summarize_episode,
    summarize_youtube_video,
    transcribe_source,
)
from podcast_tools.storage import make_episode_id

from ..app import mcp


@mcp.tool()
def podcast_list_feeds() -> str:
    """List the curated podcast feeds (name -> RSS URL) available by short name."""
    return json.dumps(list_feeds(), indent=2)


@mcp.tool()
def podcast_list_rss(rss_url: str, limit: int = 5) -> str:
    """List recent episodes from a podcast RSS feed.

    ``rss_url`` accepts a curated feed name (call podcast_list_feeds to see them; match
    is forgiving, e.g. "lex", "the tim ferriss show") or a raw RSS URL.
    """
    return json.dumps(list_rss_episodes(rss_url, limit), indent=2)


@mcp.tool()
def podcast_list_youtube(channel_id: str, limit: int = 5) -> str:
    """List recent videos from a YouTube channel id."""
    return json.dumps(list_youtube_channel_episodes(channel_id, limit), indent=2)


@mcp.tool()
def youtube_video_summariser(
    video_url: str,
    title: str = "",
    prefer_captions: bool = True,
) -> str:
    """Summarise ANY YouTube video in one step.

    Fetches the video's captions (free, instant) or transcribes the audio with
    Deepgram when captions are unavailable, then writes a detailed summary. Returns
    the episode_id, the saved transcript/summary paths, and the summary text.
    """
    result = summarize_youtube_video(
        video_url, title=title, prefer_captions=prefer_captions
    )
    return (
        f"episode_id={result['episode_id']}\n"
        f"transcript={result['transcript_path']}\n"
        f"summary={result['summary_path']}\n\n"
        f"{result['summary']}"
    )


@mcp.tool()
def podcast_transcribe(
    source_url: str,
    title: str = "",
    prefer_captions: bool = True,
) -> str:
    """Transcribe an RSS audio URL or YouTube URL and save the transcript.

    Returns the episode_id and saved path. YouTube captions are used when
    available by default; set prefer_captions=false to force audio transcription
    with Deepgram when captions look incomplete.
    """
    episode_id = make_episode_id(source_url)
    path = transcribe_source(
        source_url,
        title=title,
        episode_id=episode_id,
        prefer_captions=prefer_captions,
    )
    return f"episode_id={episode_id}\nsaved={path}"


@mcp.tool()
def podcast_summarize(episode_id: str, title: str = "") -> str:
    """Summarize a saved transcript and save it."""
    return summarize_episode(episode_id, title=title)


@mcp.tool()
def podcast_ask(episode_id: str, question: str) -> str:
    """Answer a question about a saved transcript via RAG."""
    return ask_episode(episode_id, question)
