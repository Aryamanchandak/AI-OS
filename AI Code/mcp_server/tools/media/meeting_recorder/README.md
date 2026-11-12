# `meeting_recorder`  ·  group: `media`

4 registered MCP tool(s). Everything for this tool lives in this folder.

### `chat_with_meeting(context: str, question: str, history: list[dict] = None) -> str`

Ask a follow-up question about a meeting that has already been summarised. context: the
context value returned by process_meeting_audio or summarize_meeting. question: the
question to answer. history: optional list of prior Q&A turns as [{"role":
"user"|"assistant", "content": str}]. Returns a grounded answer drawn strictly from the
meeting content.

### `process_meeting_audio(file_uri: str) -> dict`

Transcribe an audio recording and generate a structured meeting summary. file_uri: URI
returned as `uri` by upload_file_to_gemini. Returns: { "summary": str, "context": str }
Pass the context value to chat_with_meeting for follow-up questions.

### `summarize_meeting(transcript: str) -> dict`

Generate an institutional-grade meeting summary from a transcript. Strictly grounded —
only what is explicitly stated in the transcript is reported. Returns: { "summary": str,
"context": str } The context field is the same summary, formatted for use as input to
chat_with_meeting. Use chat_with_meeting afterwards for follow-up Q&A against the
meeting content.

### `transcribe_audio(file_uri: str) -> str`

Transcribe an audio recording that has been uploaded to the Gemini Files API. file_uri:
URI returned as `uri` by upload_file_to_gemini. Returns plain text transcript. Use this
standalone if you only need the transcript, or before summarize_meeting if you want to
inspect the transcript before generating a summary.

**Files:** `logic.py`, `__init__.py` (registration).
