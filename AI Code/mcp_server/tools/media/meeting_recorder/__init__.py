from tool_registry import register
from .logic import (
    transcribe_audio,
    summarize_meeting,
    process_meeting_audio,
    chat_with_meeting,
)

for _fn in (transcribe_audio, summarize_meeting, process_meeting_audio, chat_with_meeting):
    register(group="media")(_fn)
