# `youtube`  ·  group: `media`

4 registered MCP tool(s). Everything for this tool lives in this folder.

### `fetch_youtube_transcript(url: str) -> str`

Fetch and clean the transcript from a YouTube video URL. Returns plain text transcript.
Raises ValueError if captions are unavailable (auto-generated or private video). Use
this before summarize_transcript, or standalone to inspect transcript length or language
before deciding whether to summarise.

### `search_youtube(query: str) -> list[dict]`

Search YouTube for videos matching a query. Returns up to 40 results, each with:
title, url, channel, view_count, duration, thumbnail Use this before
summarize_youtube_video to find the right video URL.

### `summarize_transcript(transcript: str) -> str`

Generate an investment-analyst-style summary from a video transcript. Input: plain text
transcript from fetch_youtube_transcript or any source. Returns structured markdown
summary covering key points, data cited, investment relevance, and notable quotes.

### `summarize_youtube_video(url: str) -> str`

Fetch the transcript from a YouTube URL and generate an analyst-style summary. Returns
structured markdown. Use search_youtube first to find relevant videos, then call this
with the URL. Use component tools individually if you need the raw transcript or want to
summarise a transcript from a non-YouTube source.

**Files:** `logic.py`, `__init__.py` (registration).
