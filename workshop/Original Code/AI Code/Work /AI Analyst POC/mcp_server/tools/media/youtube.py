from tool_registry import register
from youtube_intelligence_mcp import (
    search_youtube,
    fetch_youtube_transcript,
    summarize_transcript,
    summarize_youtube_video,
)

for _fn in [search_youtube, fetch_youtube_transcript, summarize_transcript, summarize_youtube_video]:
    register(group="media")(_fn)
