from tool_registry import register
from podcast_mcp import (
    generate_podcast_transcript,
    synthesize_podcast_audio,
    run_podcast_pipeline,
)

for _fn in [generate_podcast_transcript, synthesize_podcast_audio, run_podcast_pipeline]:
    register(group="media")(_fn)
